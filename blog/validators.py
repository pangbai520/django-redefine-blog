import re
from pathlib import Path
from xml.etree import ElementTree

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from PIL import Image, UnidentifiedImageError


THEME_IMAGE_EXTENSIONS = ("jpg", "jpeg", "png", "gif", "webp", "svg")
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
