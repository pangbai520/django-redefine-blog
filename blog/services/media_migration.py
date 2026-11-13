import hashlib
import re
import shutil
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

from django.apps import apps
from django.core.cache import cache
from django.core.files.storage import FileSystemStorage
from django.core.management.base import CommandError
from django.db import models, transaction
from PIL import Image, UnidentifiedImageError

from blog.services.images import EXTENSIONS, FORMATS
from blog.services.media_storage import clean_name, walk_files


IMAGE_PREFIXES = frozenset(
    {
        "audio_covers",
        "avatar",
        "banner",
        "comment-images",
        "content-images",
        "cover",
        "editor",
        "favicon",
        "logo",
        "opengraph",
        "recommendation",
        "thumbnails",
        "user-avatars",
        "writer_avatar",
    }
)
LOCAL_MEDIA_RE = re.compile(
    r"(?<![A-Za-z0-9])(?P<url>/resources/(?P<name>[^\s\"'<>)}\]\u3002"
    r"\uff0c\uff1b\uff01\uff1f]+))"
)
CONTENT_MODELS = (
    "ArticleModel",
    "Comment",
    "StandalonePage",
    "StandalonePageTranslation",
)


def file_digest(handle):
    digest = hashlib.sha256()
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def _canonical_name(path, name):
    parts = PurePosixPath(name).parts
    if not parts or parts[0] not in IMAGE_PREFIXES:
        return name
    try:
        with Image.open(path, formats=FORMATS) as image:
            image_format = (image.format or "").upper()
            image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise CommandError(f"Cannot identify uploaded image: {name}") from exc
    extension = EXTENSIONS.get(image_format)
    if not extension:
        raise CommandError(f"Unsupported uploaded image: {name}")
    with path.open("rb") as handle:
        digest = file_digest(handle)
    parent = PurePosixPath(name).parent
    return (parent / f"{digest}.{extension}").as_posix()


def prepare_local_media(source, dry_run=False):
    """Plan canonical object keys and keep local hash-named rollback copies."""
    source = Path(source)
    storage = FileSystemStorage(location=source)
    path_map = {}
    uploads = {}
    cleanup = set()
    for old_name in sorted(walk_files(storage)):
        old_path = source / old_name
        new_name = clean_name(_canonical_name(old_path, old_name))
        upload_path = old_path
        if new_name != old_name:
            new_path = source / new_name
            if new_path.exists():
                with old_path.open("rb") as old, new_path.open("rb") as new:
                    if file_digest(old) != file_digest(new):
                        raise CommandError(
                            f"Local hash-name conflict: {new_name}"
                        )
            elif not dry_run:
                new_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(old_path, new_path)
            if new_path.exists():
                upload_path = new_path
            cleanup.add(new_path)
        path_map[old_name] = new_name
        uploads.setdefault(new_name, upload_path)
        cleanup.add(old_path)
    return path_map, uploads, cleanup


def _rewrite_content(content, targets):
    replaced = 0

    def replace(match):
        nonlocal replaced
        try:
            name = clean_name(unquote(match.group("name")))
        except CommandError:
            return match.group("url")
        target = targets.get(name)
        if not target:
            return match.group("url")
        replaced += 1
        return target

    return LOCAL_MEDIA_RE.sub(replace, content or ""), replaced


def _rewrite_files(path_map, dry_run):
    changed_refs = 0
    for model in apps.get_app_config("blog").get_models():
        for field in model._meta.concrete_fields:
            if not isinstance(field, models.FileField):
                continue
            changed = []
            queryset = model.objects.exclude(**{field.name: ""}).only(
                "pk", field.name
            )
            for obj in queryset.iterator(chunk_size=200):
                field_file = getattr(obj, field.name)
                new_name = path_map.get(field_file.name)
                if not new_name or new_name == field_file.name:
                    continue
                setattr(obj, field.name, new_name)
                changed.append(obj)
            changed_refs += len(changed)
            if changed and not dry_run:
                model.objects.bulk_update(
                    changed,
                    (field.name,),
                    batch_size=200,
                )
    return changed_refs


def rewrite_database(path_map, targets, *, rewrite_urls=True, dry_run=False):
    """Update stored file keys and verified local media links atomically."""
    changed_rows = 0
    changed_urls = 0
    with transaction.atomic():
        changed_refs = _rewrite_files(path_map, dry_run)
        if rewrite_urls:
            for model_name in CONTENT_MODELS:
                model = apps.get_model("blog", model_name)
                changed = []
                for obj in model.objects.only("pk", "content").iterator(
                    chunk_size=200
                ):
                    content, count = _rewrite_content(obj.content, targets)
                    if not count:
                        continue
                    obj.content = content
                    changed.append(obj)
                    changed_urls += count
                changed_rows += len(changed)
                if changed and not dry_run:
                    model.objects.bulk_update(
                        changed,
                        ("content",),
                        batch_size=200,
                    )
        if not dry_run and (changed_refs or changed_rows):
            transaction.on_commit(cache.clear)
    return changed_refs, changed_rows, changed_urls
