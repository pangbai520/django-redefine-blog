import hashlib
import logging
import warnings
from dataclasses import dataclass
from datetime import timedelta
from io import BytesIO
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.cache import cache
from django.utils import timezone
from PIL import Image, ImageOps, ImageSequence, UnidentifiedImageError


FORMATS = ("JPEG", "PNG", "GIF", "WEBP")
EXTENSIONS = {"JPEG": "jpg", "PNG": "png", "GIF": "gif", "WEBP": "webp"}
logger = logging.getLogger(__name__)
ORPHAN_IMAGE_CLEANUP_CACHE_KEY = "blog:comment-images:orphan-cleanup"
ORPHAN_IMAGE_MAX_AGE_HOURS = 24
ORPHAN_IMAGE_CLEANUP_INTERVAL = 24 * 60 * 60
ORPHAN_IMAGE_CLEANUP_BATCH_SIZE = 200


class ImageUploadError(ValueError):
    pass


@dataclass(frozen=True)
class CleanImage:
    file: ContentFile
    digest: str
    extension: str
    width: int
    height: int
    frames: int


def _save_static(image, output, image_format):
    image = ImageOps.exif_transpose(image)
    if image_format == "JPEG":
        if image.mode not in {"RGB", "L"}:
            image = image.convert("RGB")
        image.save(output, "JPEG", quality=92, optimize=True)
    elif image_format == "PNG":
        image.save(output, "PNG", optimize=True)
    elif image_format == "WEBP":
        image.save(output, "WEBP", quality=92, method=4)
    else:
        image.save(output, "GIF")


def _save_animated(image, output, image_format):
    frames = [frame.convert("RGBA").copy() for frame in ImageSequence.Iterator(image)]
    durations = [
        int(frame.info.get("duration", image.info.get("duration", 0)) or 0)
        for frame in ImageSequence.Iterator(image)
    ]
    options = {
        "save_all": True,
        "append_images": frames[1:],
        "duration": durations,
        "loop": int(image.info.get("loop", 0) or 0),
    }
    if image_format == "WEBP":
        options.update({"quality": 92, "method": 4})
    else:
        options["disposal"] = 2
    frames[0].save(output, image_format, **options)


def clean_image(upload, *, max_bytes, max_dimension, max_pixels):
    """Validate, orient and re-encode a raster image without private metadata."""
    if not upload or getattr(upload, "size", 0) > max_bytes:
        raise ImageUploadError("size")

    try:
        upload.seek(0)
        source = upload.read()
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(source), formats=FORMATS) as probe:
                image_format = (probe.format or "").upper()
                width, height = probe.size
                frames = max(int(getattr(probe, "n_frames", 1) or 1), 1)
                probe.verify()
            if image_format not in EXTENSIONS:
                raise ImageUploadError("type")
            if max(width, height) > max_dimension:
                raise ImageUploadError("dimensions")
            if width * height * frames > max_pixels:
                raise ImageUploadError("pixels")

            output = BytesIO()
            with Image.open(BytesIO(source), formats=FORMATS) as image:
                if frames > 1 and image_format in {"GIF", "WEBP"}:
                    _save_animated(image, output, image_format)
                else:
                    _save_static(image, output, image_format)
    except ImageUploadError:
        raise
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
    ) as exc:
        raise ImageUploadError("invalid") from exc
    finally:
        try:
            upload.seek(0)
        except (AttributeError, OSError):
            pass

    data = output.getvalue()
    if len(data) > max_bytes:
        raise ImageUploadError("size")
    extension = EXTENSIONS[image_format]
    stem = Path(getattr(upload, "name", "image")).stem or "image"
    return CleanImage(
        file=ContentFile(data, name=f"{stem}.{extension}"),
        digest=hashlib.sha256(data).hexdigest(),
        extension=extension,
        width=width,
        height=height,
        frames=frames,
    )


def clean_field(field_file, *, max_bytes, max_dimension, max_pixels):
    """Replace one newly assigned FieldFile with its canonical safe encoding."""
    if not field_file or getattr(field_file, "_committed", True):
        return
    cleaned = clean_image(
        field_file.file,
        max_bytes=max_bytes,
        max_dimension=max_dimension,
        max_pixels=max_pixels,
    )
    field_file.name = cleaned.file.name
    field_file._file = cleaned.file
    field_file._committed = False


def maybe_clean_images():
    """Bound automatic comment-image cleanup to one small daily batch."""
    if not cache.add(
        ORPHAN_IMAGE_CLEANUP_CACHE_KEY,
        True,
        ORPHAN_IMAGE_CLEANUP_INTERVAL,
    ):
        return 0
    try:
        from blog.models import CommentImage

        cutoff = timezone.now() - timedelta(hours=ORPHAN_IMAGE_MAX_AGE_HOURS)
        orphan_ids = list(
            CommentImage.objects.filter(
                comment__isnull=True,
                created_at__lt=cutoff,
            )
            .order_by("created_at")
            .values_list("pk", flat=True)[:ORPHAN_IMAGE_CLEANUP_BATCH_SIZE]
        )
        for image in CommentImage.objects.filter(pk__in=orphan_ids).iterator():
            image.delete()
        if len(orphan_ids) == ORPHAN_IMAGE_CLEANUP_BATCH_SIZE:
            cache.set(ORPHAN_IMAGE_CLEANUP_CACHE_KEY, True, 10 * 60)
        return len(orphan_ids)
    except Exception:
        cache.delete(ORPHAN_IMAGE_CLEANUP_CACHE_KEY)
        logger.exception("Failed to clean orphaned comment images")
        return 0
