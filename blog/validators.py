import re
from pathlib import Path
from xml.etree import ElementTree

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.utils.translation import gettext_lazy as _
from PIL import Image, UnidentifiedImageError


THEME_IMAGE_EXTENSIONS = ("jpg", "jpeg", "png", "gif", "webp", "svg")
PROFILE_AVATAR_EXTENSIONS = ("jpg", "jpeg", "png", "gif", "webp")
_SVG_UNSAFE_CONTENT = re.compile(
    rb"(?:<!doctype|<!entity|<script\b|\bon[a-z]+\s*=|javascript:|data:text/html)",
    re.IGNORECASE,
)
_SVG_EXTERNAL_REFERENCE = re.compile(
    rb"(?:href|xlink:href)\s*=\s*['\"]\s*(?:https?:|//|data:)",
    re.IGNORECASE,
)


def validate_theme_image(upload):
    """Accept normal web images and self-contained, script-free SVG files."""
    FileExtensionValidator(THEME_IMAGE_EXTENSIONS)(upload)
    # Model validation can receive a stored FieldFile rather than a new upload;
    # the upload itself has already been checked by the form in that case.
    if getattr(upload, "_committed", False):
        return
    suffix = Path(upload.name).suffix.lower()
    position = upload.tell()
    try:
        upload.seek(0)
        if suffix == ".svg":
            payload = upload.read(2 * 1024 * 1024 + 1)
            if len(payload) > 2 * 1024 * 1024:
                raise ValidationError("SVG files must be no larger than 2 MB.")
            if _SVG_UNSAFE_CONTENT.search(payload) or _SVG_EXTERNAL_REFERENCE.search(payload):
                raise ValidationError("SVG files cannot contain scripts or external resources.")
            try:
                root = ElementTree.fromstring(payload)
            except ElementTree.ParseError as exc:
                raise ValidationError("Upload a valid SVG file.") from exc
            if root.tag.rsplit("}", 1)[-1].lower() != "svg":
                raise ValidationError("Upload a valid SVG file.")
            return

        try:
            image = Image.open(upload)
            image.verify()
        except (UnidentifiedImageError, OSError, SyntaxError) as exc:
            raise ValidationError("Upload a valid image file.") from exc
    finally:
        upload.seek(position)


def validate_profile_avatar(upload):
    """Accept bounded raster avatars and reject disguised or decompression-heavy files."""
    FileExtensionValidator(PROFILE_AVATAR_EXTENSIONS)(upload)
    if getattr(upload, "_committed", False):
        return

    max_bytes = getattr(settings, "PROFILE_AVATAR_MAX_BYTES", 2 * 1024 * 1024)
    if getattr(upload, "size", 0) > max_bytes:
        raise ValidationError(
            _("Avatar images must be no larger than %(size)s MB."),
            params={"size": max_bytes // (1024 * 1024)},
        )

    expected_formats = {
        ".jpg": {"JPEG"},
        ".jpeg": {"JPEG"},
        ".png": {"PNG"},
        ".gif": {"GIF"},
        ".webp": {"WEBP"},
    }
    suffix = Path(upload.name).suffix.lower()
    position = upload.tell()
    try:
        upload.seek(0)
        image = Image.open(upload)
        image_format = (image.format or "").upper()
        width, height = image.size
        frames = max(int(getattr(image, "n_frames", 1) or 1), 1)
        if image_format not in expected_formats.get(suffix, set()):
            raise ValidationError(
                _("Avatar image data does not match its filename extension.")
            )
        if max(width, height) > getattr(settings, "PROFILE_AVATAR_MAX_DIMENSION", 4096):
            raise ValidationError(_("Avatar dimensions are too large."))
        if width * height * frames > getattr(settings, "PROFILE_AVATAR_MAX_PIXELS", 16_000_000):
            raise ValidationError(
                _("Avatar contains too many pixels or animation frames.")
            )
        image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise ValidationError(_("Upload a valid avatar image.")) from exc
    finally:
        upload.seek(position)
