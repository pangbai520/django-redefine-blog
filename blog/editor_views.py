import hashlib
import warnings
from pathlib import Path

from django.conf import settings
from django.db.models import Count
from django.http import JsonResponse
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.clickjacking import xframe_options_sameorigin
from PIL import Image, UnidentifiedImageError

from blog.models import EditorImage
from blog.services.editor_images import image_used, store_image


def _upload_error(message, status=400):
    return JsonResponse(
        {"success": 0, "message": str(message), "url": ""}, status=status
    )


def _can_edit(user):
    return (
        user.is_authenticated
        and user.is_active
        and user.is_staff
        and (
            user.has_perm("blog.add_articlemodel")
            or user.has_perm("blog.change_articlemodel")
        )
    )


@require_POST
@xframe_options_sameorigin
def editor_image_upload(request):
    """Accept editor images only from staff who can create or edit articles."""
    user = request.user
    if not user.is_authenticated:
        return _upload_error(_("Sign in to upload images."), 403)
    if not _can_edit(user):
        return _upload_error(
            _("You do not have permission to upload article images."), 403
        )

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
    try:
        image = store_image(
            upload,
            digest.hexdigest(),
            extension,
            user,
            width,
            height,
        )
    except Exception:
        return _upload_error(_("Image upload failed. Please try again later."), 500)
    return JsonResponse(
        {
            "success": 1,
            "message": str(_("Upload complete.")),
            "id": image.pk,
            "url": image.image.url,
        }
    )


@require_GET
@never_cache
def editor_image_list(request):
    if not _can_edit(request.user):
        return JsonResponse({"detail": str(_("Permission denied."))}, status=403)

    try:
        page = max(int(request.GET.get("page", "1")), 1)
    except ValueError:
        page = 1
    page_size = 48
    offset = (page - 1) * page_size
    queryset = (
        EditorImage.objects.select_related("uploader")
        .annotate(ref_count=Count("refs"))
        .order_by("-created_at", "-pk")
    )
    total = queryset.count()
    images = []
    for image in queryset[offset : offset + page_size]:
        images.append(
            {
                "id": image.pk,
                "name": image.original_name or Path(image.image.name).name,
                "url": image.image.url,
                "width": image.width,
                "height": image.height,
                "size": image.size,
                "created": image.created_at.isoformat(),
                "ref_count": image.ref_count,
                "delete_url": reverse("mdeditor_image_delete", args=(image.pk,)),
            }
        )
    return JsonResponse(
        {
            "images": images,
            "page": page,
            "has_next": offset + page_size < total,
        }
    )


@require_POST
def editor_image_delete(request, image_id):
    if not _can_edit(request.user):
        return JsonResponse({"detail": str(_("Permission denied."))}, status=403)
    image = EditorImage.objects.filter(pk=image_id).first()
    if image is None:
        return JsonResponse({"detail": str(_("Image not found."))}, status=404)
    if image_used(image):
        return JsonResponse(
            {"detail": str(_("This image is still used by published content."))},
            status=409,
        )
    image.delete()
    return JsonResponse({"deleted": True})
