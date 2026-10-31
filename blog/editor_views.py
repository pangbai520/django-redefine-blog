import hashlib
import warnings
from pathlib import Path

from django.conf import settings
from django.core.files.storage import default_storage
from django.http import JsonResponse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from django.views.decorators.clickjacking import xframe_options_sameorigin
from PIL import Image, UnidentifiedImageError


def _upload_error(message, status=400):
    return JsonResponse({"success": 0, "message": str(message), "url": ""}, status=status)


@require_POST
@xframe_options_sameorigin
def editor_image_upload(request):
    """Accept editor images only from staff who can create or edit articles."""
    user = request.user
    if not user.is_authenticated:
        return _upload_error(_("Sign in to upload images."), 403)
    if not user.is_active or not user.is_staff or not (
        user.has_perm("blog.add_articlemodel")
        or user.has_perm("blog.change_articlemodel")
    ):
        return _upload_error(_("You do not have permission to upload article images."), 403)

    upload = request.FILES.get("editormd-image-file")
    max_bytes = settings.EDITOR_UPLOAD_MAX_BYTES
    if not upload or upload.size > max_bytes:
        return _upload_error(
            _("Image must be smaller than %(size)s MB.")
            % {"size": max_bytes // (1024 * 1024)}
        )

    suffix = Path(upload.name).suffix.lower()
    expected_formats = {
        ".jpg": {"JPEG"},
        ".jpeg": {"JPEG"},
        ".png": {"PNG"},
        ".gif": {"GIF"},
        ".webp": {"WEBP"},
    }
    if suffix not in expected_formats:
        return _upload_error(_("Unsupported image type."))

    try:
        upload.seek(0)
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(upload, formats=("JPEG", "PNG", "GIF", "WEBP")) as image:
                detected_format = image.format
                width, height = image.size
                frames = max(int(getattr(image, "n_frames", 1) or 1), 1)
                if detected_format not in expected_formats[suffix]:
                    return _upload_error(
                        _("Image data does not match its filename extension.")
                    )
                if max(width, height) > settings.EDITOR_UPLOAD_MAX_DIMENSION:
                    return _upload_error(_("Image dimensions are too large."))
                if width * height * frames > settings.EDITOR_UPLOAD_MAX_PIXELS:
                    return _upload_error(
                        _("Image contains too many pixels or animation frames.")
                    )
                image.verify()
        upload.seek(0)
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
    ):
        return _upload_error(_("Image data is invalid."))

    extension = "jpg" if detected_format == "JPEG" else detected_format.lower()
    upload.seek(0)
    digest = hashlib.sha256()
    for chunk in upload.chunks():
        digest.update(chunk)
    upload.seek(0)
    path = f"editor/{digest.hexdigest()}.{extension}"
    try:
        if default_storage.exists(path):
            saved = path
        else:
            saved = default_storage.save(path, upload)
            # FileSystemStorage avoids overwrites by adding a suffix. Two
            # simultaneous uploads of identical bytes can therefore both pass
            # the exists() check. Keep the canonical digest path and discard
            # the racing duplicate once the first request has created it.
            if saved != path and default_storage.exists(path):
                default_storage.delete(saved)
                saved = path
    except Exception:
        return _upload_error(_("Image upload failed. Please try again later."), 500)
    return JsonResponse(
        {
            "success": 1,
            "message": str(_("Upload complete.")),
            "url": default_storage.url(saved),
        }
    )
