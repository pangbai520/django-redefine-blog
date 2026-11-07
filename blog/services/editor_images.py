import re
from pathlib import Path

from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from PIL import Image, UnidentifiedImageError

from blog.models import (
    ArticleModel,
    EditorImage,
    EditorImageLease,
    EditorImageRef,
    StandalonePage,
    StandalonePageTranslation,
)

IMAGE_RE = re.compile(
    r"(?P<path>(?:content-images|editor)/(?P<digest>[0-9a-f]{64})\.(?:jpe?g|png|gif|webp))",
    re.IGNORECASE,
)


def image_paths(content):
    return {
        (match.group("digest").lower(), match.group("path"))
        for match in IMAGE_RE.finditer(content or "")
    }


def _image_meta(path):
    size = 0
    width = 0
    height = 0
    try:
        size = default_storage.size(path)
        with default_storage.open(path, "rb") as stored:
            with Image.open(stored) as image:
                width, height = image.size
    except (OSError, ValueError, UnidentifiedImageError):
        pass
    return size, width, height


def _register_path(digest, path):
    image = EditorImage.objects.filter(digest=digest).first()
    if image or not default_storage.exists(path):
        return image
    size, width, height = _image_meta(path)
    try:
        return EditorImage.objects.create(
            image=path,
            digest=digest,
            original_name=Path(path).name,
            size=size,
            width=width,
            height=height,
        )
    except IntegrityError:
        return EditorImage.objects.filter(digest=digest).first()


def store_image(upload, digest, extension, user, width, height):
    path = f"content-images/{digest}.{extension}"
    image = EditorImage.objects.filter(digest=digest).first()
    if image and default_storage.exists(image.image.name):
        return image

    if not default_storage.exists(path):
        saved = default_storage.save(path, upload)
        if saved != path and default_storage.exists(path):
            default_storage.delete(saved)
        elif saved != path:
            path = saved

    defaults = {
        "image": path,
        "original_name": Path(upload.name).name[:255],
        "uploader": user,
        "size": upload.size,
        "width": width,
        "height": height,
    }
    try:
        with transaction.atomic():
            image, created = EditorImage.objects.get_or_create(
                digest=digest, defaults=defaults
            )
    except IntegrityError:
        image = EditorImage.objects.get(digest=digest)
        created = False

    if not created and not default_storage.exists(image.image.name):
        image.image.name = path
        image.original_name = defaults["original_name"]
        image.uploader = user
        image.size = upload.size
        image.width = width
        image.height = height
        image.save()
    return image


def sync_refs(target_type, target_id, content):
    found = image_paths(content)
    images = []
    for digest, path in found:
        image = EditorImage.objects.filter(digest=digest).first()
        if image is None:
            image = _register_path(digest, path)
        if image is not None:
            images.append(image)

    keep = [image.pk for image in images]
    refs = EditorImageRef.objects.filter(
        target_type=target_type, target_id=target_id
    )
    if keep:
        refs.exclude(image_id__in=keep).delete()
    else:
        refs.delete()
    EditorImageRef.objects.bulk_create(
        [
            EditorImageRef(
                image=image, target_type=target_type, target_id=target_id
            )
            for image in images
        ],
        ignore_conflicts=True,
    )


def drop_refs(target_type, target_id):
    EditorImageRef.objects.filter(
        target_type=target_type, target_id=target_id
    ).delete()


def index_files():
    count = 0
    for folder in ("content-images", "editor"):
        try:
            _dirs, names = default_storage.listdir(folder)
        except (FileNotFoundError, NotImplementedError, OSError):
            continue
        for name in names:
            match = IMAGE_RE.fullmatch(f"{folder}/{name}")
            if not match:
                continue
            if _register_path(match.group("digest").lower(), match.group("path")):
                count += 1
    return count


def rebuild_refs():
    index_files()
    images = {image.digest: image for image in EditorImage.objects.all()}
    sources = (
        (EditorImageRef.ARTICLE, ArticleModel.objects.all()),
        (EditorImageRef.PAGE, StandalonePage.objects.all()),
        (
            EditorImageRef.TRANSLATION,
            StandalonePageTranslation.objects.all(),
        ),
    )
    refs = []
    for target_type, queryset in sources:
        for obj in queryset.only("pk", "content").iterator():
            digests = {digest for digest, _path in image_paths(obj.content)}
            refs.extend(
                EditorImageRef(
                    image=images[digest],
                    target_type=target_type,
                    target_id=obj.pk,
                )
                for digest in digests
                if digest in images
            )
    with transaction.atomic():
        EditorImageRef.objects.all().delete()
        EditorImageRef.objects.bulk_create(refs, ignore_conflicts=True)


def image_used(image):
    if image.refs.exists() or image.leases.exists():
        return True
    digest = image.digest
    return (
        ArticleModel.objects.filter(content__contains=digest).exists()
        or StandalonePage.objects.filter(content__contains=digest).exists()
        or StandalonePageTranslation.objects.filter(content__contains=digest).exists()
    )


def lease_image(image, user, draft_id):
    with transaction.atomic():
        image = EditorImage.objects.select_for_update().get(pk=image.pk)
        EditorImageLease.objects.get_or_create(
            image=image,
            owner=user,
            draft_id=draft_id,
        )


def release_draft(user, draft_id):
    with transaction.atomic():
        image_ids = list(
            EditorImageLease.objects.filter(
                owner=user, draft_id=draft_id
            ).values_list("image_id", flat=True)
        )
        images = list(
            EditorImage.objects.select_for_update().filter(pk__in=image_ids)
        )
        EditorImageLease.objects.filter(owner=user, draft_id=draft_id).delete()
        deleted = 0
        for image in images:
            if not image_used(image):
                image.delete()
                deleted += 1
    return deleted
