import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from contextlib import contextmanager
from io import StringIO
from pathlib import Path, PurePosixPath

from django.apps import apps
from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import transaction
from django.db.models.signals import post_delete


ARCHIVE_FORMAT = "django-redefine-blog-data"
LEGACY_ARCHIVE_FORMATS = {
    "django-redefine-blog-data",
    "pangbaiblog-portable-data",
}
SUPPORTED_ARCHIVE_FORMATS = {ARCHIVE_FORMAT, *LEGACY_ARCHIVE_FORMATS}
ARCHIVE_VERSION = 1


def _media_files(exclude=()):
    root = Path(settings.MEDIA_ROOT)
    if not root.exists():
        return []
    excluded = {Path(path).resolve() for path in exclude}
    return [
        path
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink() and path.resolve() not in excluded
    ]


def export_archive(output_path, include_traffic=False):
    """Export database content and uploaded files into one portable archive."""
    output_path = Path(output_path).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = StringIO()
    excludes = [] if include_traffic else ["blog.trafficmodel"]
    call_command(
        "dumpdata",
        "auth.Group",
        "auth.User",
        "blog",
        natural_foreign=True,
        natural_primary=True,
        exclude=excludes,
        indent=2,
        stdout=serialized,
    )
    payload = serialized.getvalue().encode("utf-8")
    media_root = Path(settings.MEDIA_ROOT)
    # avoid recursively embedding a previous archive when the destination sits
    # below MEDIA_ROOT, which is convenient but otherwise unsafe on overwrite
    media_files = _media_files(exclude=(output_path,))
    manifest = {
        "format": ARCHIVE_FORMAT,
        "version": ARCHIVE_VERSION,
        "data_sha256": hashlib.sha256(payload).hexdigest(),
        "includes_traffic": include_traffic,
        "media_files": len(media_files),
    }
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr("data.json", payload)
        for path in media_files:
            archive.write(path, "media/" + path.relative_to(media_root).as_posix())
    return manifest


def _validate_archive(archive):
    try:
        manifest = json.loads(archive.read("manifest.json"))
        payload = archive.read("data.json")
    except (KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CommandError("This is not a valid Django Redefine Blog data archive.") from exc
    if not isinstance(manifest, dict):
        raise CommandError("This is not a valid Django Redefine Blog data archive.")
    if manifest.get("format") not in SUPPORTED_ARCHIVE_FORMATS or manifest.get("version") != ARCHIVE_VERSION:
        raise CommandError("The archive format or version is not supported.")
    if hashlib.sha256(payload).hexdigest() != manifest.get("data_sha256"):
        raise CommandError("The archive database payload is corrupted.")
    member_names = set()
    for member in archive.infolist():
        path = PurePosixPath(member.filename)
        if member.filename in member_names:
            raise CommandError("The archive contains a duplicate file path.")
        member_names.add(member.filename)
        if path.is_absolute() or ".." in path.parts:
            raise CommandError("The archive contains an unsafe file path.")
        if member.filename not in {"manifest.json", "data.json"} and path.parts[:1] != ("media",):
            raise CommandError("The archive contains an unexpected file.")
    return manifest, payload


def _blog_has_data():
    return any(model.objects.exists() for model in apps.get_app_config("blog").get_models())


def _clear_blog_data():
    # reverse registration order so child rows disappear before their parents
    for model in reversed(list(apps.get_app_config("blog").get_models())):
        model.objects.all().delete()


@contextmanager
def _suspend_cleanup_deletes():
    """Keep django-cleanup from deleting files while a full archive is restored."""
    try:
        from django_cleanup import cache as cleanup_cache
        from django_cleanup import handlers as cleanup_handlers
    except ImportError:  # pragma: no cover - django-cleanup is a required dependency
        yield
        return

    disconnected = []
    for model in cleanup_cache.cleanup_models():
        dispatch_uid = f"post_delete_django_cleanup_{cleanup_cache.get_model_name(model)}"
        if post_delete.disconnect(sender=model, dispatch_uid=dispatch_uid):
            disconnected.append((model, dispatch_uid))
    try:
        yield
    finally:
        for model, dispatch_uid in disconnected:
            post_delete.connect(
                cleanup_handlers.delete_all_post_delete,
                sender=model,
                dispatch_uid=dispatch_uid,
            )


def _extract_media(archive, destination_root):
    destination_root.mkdir(parents=True, exist_ok=True)
    for member in archive.infolist():
        path = PurePosixPath(member.filename)
        if member.is_dir() or path.parts[:1] != ("media",):
            continue
        relative = Path(*path.parts[1:])
        destination = (destination_root / relative).resolve()
        try:
            destination.relative_to(destination_root)
        except ValueError as exc:  # defensive; _validate_archive checks this too
            raise CommandError("The archive contains an unsafe media path.") from exc
        destination.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member, "r") as source, destination.open("xb") as target:
            shutil.copyfileobj(source, target, length=1024 * 1024)


def _swap_media_tree(staged_root, media_root, previous_root):
    had_previous = media_root.exists()
    if had_previous:
        os.replace(media_root, previous_root)
    try:
        os.replace(staged_root, media_root)
    except Exception:
        if had_previous:
            os.replace(previous_root, media_root)
        raise
    return had_previous


def _roll_back_media_tree(media_root, previous_root, had_previous):
    if media_root.exists():
        shutil.rmtree(media_root)
    if had_previous and previous_root.exists():
        os.replace(previous_root, media_root)


def import_archive(input_path, replace=False):
    """Restore a portable archive into an empty or explicitly replaced blog."""
    input_path = Path(input_path).expanduser().resolve()
    if not input_path.is_file():
        raise CommandError(f"Archive not found: {input_path}")
    if _blog_has_data() and not replace:
        raise CommandError("Blog data already exists; pass --replace to restore this archive.")

    media_root = Path(settings.MEDIA_ROOT).resolve()
    temporary_parent = media_root.parent
    temporary_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="django-redefine-import-",
        dir=temporary_parent,
        ignore_cleanup_errors=True,
    ) as temporary:
        temporary_root = Path(temporary)
        staged_media = temporary_root / "media"
        previous_media = temporary_root / "previous-media"
        fixture = temporary_root / "data.json"
        try:
            with zipfile.ZipFile(input_path, "r") as archive:
                manifest, payload = _validate_archive(archive)
                fixture.write_bytes(payload)
                _extract_media(archive, staged_media)
        except (OSError, zipfile.BadZipFile) as exc:
            raise CommandError("The archive could not be read completely.") from exc

        # A backup selected from inside MEDIA_ROOT must survive the directory swap.
        try:
            archive_relative = input_path.relative_to(media_root)
        except ValueError:
            archive_relative = None
        if archive_relative is not None:
            preserved_archive = staged_media / archive_relative
            preserved_archive.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(input_path, preserved_archive)

        media_swapped = False
        had_previous_media = False
        try:
            with _suspend_cleanup_deletes(), transaction.atomic():
                if replace:
                    _clear_blog_data()
                call_command("loaddata", str(fixture), verbosity=0)
                had_previous_media = _swap_media_tree(
                    staged_media, media_root, previous_media
                )
                media_swapped = True
        except Exception:
            if media_swapped:
                _roll_back_media_tree(
                    media_root, previous_media, had_previous_media
                )
            raise
    cache.delete_many(("actived_site_config", "site_stats_counts", "site_traffic", "total_word_count"))
    return manifest
