import hashlib
import json
import tempfile
import zipfile
from io import StringIO
from pathlib import Path, PurePosixPath

from django.apps import apps
from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import transaction


ARCHIVE_FORMAT = "django-redefine-blog-data"
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
    if manifest.get("format") != ARCHIVE_FORMAT or manifest.get("version") != ARCHIVE_VERSION:
        raise CommandError("The archive format or version is not supported.")
    if hashlib.sha256(payload).hexdigest() != manifest.get("data_sha256"):
        raise CommandError("The archive database payload is corrupted.")
    for member in archive.infolist():
        path = PurePosixPath(member.filename)
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


def import_archive(input_path, replace=False):
    """Restore a portable archive into an empty or explicitly replaced blog."""
    input_path = Path(input_path).expanduser().resolve()
    if not input_path.is_file():
        raise CommandError(f"Archive not found: {input_path}")
    with zipfile.ZipFile(input_path, "r") as archive:
        manifest, payload = _validate_archive(archive)
        if _blog_has_data() and not replace:
            raise CommandError("Blog data already exists; pass --replace to restore this archive.")
        # use the media volume for temporary restore data, because production
        # containers may intentionally mount the operating-system temp read-only
        temporary_parent = Path(settings.MEDIA_ROOT).resolve().parent
        temporary_parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="django-redefine-import-", dir=temporary_parent
        ) as temporary:
            fixture = Path(temporary) / "data.json"
            fixture.write_bytes(payload)
            with transaction.atomic():
                if replace:
                    _clear_blog_data()
                call_command("loaddata", str(fixture), verbosity=0)

        media_root = Path(settings.MEDIA_ROOT).resolve()
        media_root.mkdir(parents=True, exist_ok=True)
        for member in archive.infolist():
            path = PurePosixPath(member.filename)
            if member.is_dir() or path.parts[:1] != ("media",):
                continue
            relative = Path(*path.parts[1:])
            destination = (media_root / relative).resolve()
            try:
                destination.relative_to(media_root)
            except ValueError as exc:
                raise CommandError("The archive contains an unsafe media path.") from exc
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member, "r") as source, destination.open("wb") as target:
                while chunk := source.read(1024 * 1024):
                    target.write(chunk)
    cache.delete_many(("actived_site_config", "site_stats_counts", "site_traffic", "total_word_count"))
    return manifest
