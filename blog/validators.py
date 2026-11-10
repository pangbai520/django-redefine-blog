import warnings
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.utils.translation import gettext_lazy as _
from PIL import Image, UnidentifiedImageError

THEME_IMAGE_EXTENSIONS = ("jpg", "jpeg", "png", "gif", "webp")
PROFILE_AVATAR_EXTENSIONS = ("jpg", "jpeg", "png", "gif", "webp")
AUDIO_EXTENSIONS = ("aac", "flac", "m4a", "mp3", "ogg", "opus", "wav")


def validate_theme_image(upload):
    """Accept bounded raster images; uploaded SVG is active content."""
    FileExtensionValidator(THEME_IMAGE_EXTENSIONS)(upload)
    # Model validation can receive a stored FieldFile rather than a new upload;
    # the upload itself has already been checked by the form in that case.
    if getattr(upload, "_committed", False):
        return
    max_bytes = getattr(settings, "THEME_IMAGE_MAX_BYTES", 5 * 1024 * 1024)
    if getattr(upload, "size", 0) > max_bytes:
        raise ValidationError(
            _("Images must be no larger than %(size)s MB."),
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
        try:
            image = Image.open(upload)
            image_format = (image.format or "").upper()
            width, height = image.size
            frames = max(int(getattr(image, "n_frames", 1) or 1), 1)
            if image_format not in expected_formats.get(suffix, set()):
                raise ValidationError(
                    _("Image data does not match its filename extension.")
                )
            if max(width, height) > getattr(
                settings, "THEME_IMAGE_MAX_DIMENSION", 8192
            ):
                raise ValidationError(_("Image dimensions are too large."))
            if width * height * frames > getattr(
                settings, "THEME_IMAGE_MAX_PIXELS", 24_000_000
            ):
                raise ValidationError(
                    _("Image contains too many pixels or animation frames.")
                )
            image.verify()
        except (UnidentifiedImageError, OSError, SyntaxError) as exc:
            raise ValidationError("Upload a valid image file.") from exc
    finally:
        upload.seek(position)


def validate_audio(upload):
    """Reject executable files disguised as an audio upload."""
    FileExtensionValidator(AUDIO_EXTENSIONS)(upload)
    if getattr(upload, "_committed", False):
        return

    max_bytes = getattr(settings, "AUDIO_UPLOAD_MAX_BYTES", 5 * 1024 * 1024)
    if getattr(upload, "size", 0) > max_bytes:
        raise ValidationError(
            _("Audio files must be no larger than %(size)s MB."),
            params={"size": max_bytes // (1024 * 1024)},
        )

    suffix = Path(upload.name).suffix.lower()
    position = upload.tell()
    try:
        upload.seek(0)
        header = upload.read(64)
    finally:
        upload.seek(position)

    checks = {
        ".aac": lambda data: len(data) >= 2
        and data[0] == 0xFF
        and data[1] & 0xF6 == 0xF0,
        ".flac": lambda data: data.startswith(b"fLaC"),
        ".m4a": lambda data: len(data) >= 12 and data[4:8] == b"ftyp",
        ".mp3": lambda data: data.startswith(b"ID3")
        or (len(data) >= 2 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0),
        ".ogg": lambda data: data.startswith(b"OggS"),
        ".opus": lambda data: data.startswith(b"OggS"),
        ".wav": lambda data: len(data) >= 12
        and data.startswith(b"RIFF")
        and data[8:12] == b"WAVE",
    }
    if not checks.get(suffix, lambda data: False)(header):
        raise ValidationError(_("Audio data does not match its filename extension."))


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
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(upload, formats=("JPEG", "PNG", "GIF", "WEBP")) as image:
                image_format = (image.format or "").upper()
                width, height = image.size
                if image_format not in expected_formats.get(suffix, set()):
                    raise ValidationError(
                        _("Avatar image data does not match its filename extension.")
                    )
                if max(width, height) > getattr(settings, "PROFILE_AVATAR_MAX_DIMENSION", 4096):
                    raise ValidationError(_("Avatar dimensions are too large."))
                frames = max(int(getattr(image, "n_frames", 1) or 1), 1)
                if width * height * frames > getattr(
                    settings, "PROFILE_AVATAR_MAX_PIXELS", 16_000_000
                ):
                    raise ValidationError(
                        _("Avatar contains too many pixels or animation frames.")
                    )
                image.verify()
    except (
        UnidentifiedImageError, OSError, SyntaxError, ValueError,
        Image.DecompressionBombWarning, Image.DecompressionBombError,
    ) as exc:
        raise ValidationError(_("Upload a valid avatar image.")) from exc
    finally:
        upload.seek(position)
