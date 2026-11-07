import hashlib
import logging
import uuid
import warnings
from pathlib import Path

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.http import JsonResponse
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.clickjacking import xframe_options_sameorigin
from PIL import Image, UnidentifiedImageError

from blog.models import EditorImage, EditorImageFolder
from blog.services.editor_images import (
    image_used,
    lease_image,
    release_draft,
    store_image,
)

logger = logging.getLogger(__name__)


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


def _folder_name(value):
    return " ".join((value or "").split())


def _get_folder(value):
    try:
        folder_id = int(value)
    except (TypeError, ValueError):
        return None
    return EditorImageFolder.objects.filter(pk=folder_id).first()


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
    draft_id = request.POST.get("draft_id", "").strip()
    draft_uuid = None
    if draft_id:
        try:
            draft_uuid = uuid.UUID(draft_id)
        except ValueError:
            return _upload_error(_("Invalid editor draft."))
    folder = None
    folder_supplied = "folder_id" in request.POST
    folder_id = request.POST.get("folder_id", "").strip()
    if folder_id:
        folder = _get_folder(folder_id)
        if folder is None:
            return _upload_error(_("Image folder not found."))

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
        if draft_uuid:
            lease_image(image, user, draft_uuid)
        if folder_supplied and image.folder_id != getattr(folder, "pk", None):
            image.folder = folder
            image.save(update_fields=("folder",))
    except Exception:
        logger.exception(
            "Failed to store editor image for user %s",
            user.pk,
        )
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
        EditorImage.objects.select_related("uploader", "folder")
        .annotate(
            ref_count=Count("refs", distinct=True),
            lease_count=Count("leases", distinct=True),
        )
        .order_by("-created_at", "-pk")
    )
    folder_filter = request.GET.get("folder", "all")
    if folder_filter == "uncategorized":
        queryset = queryset.filter(folder__isnull=True)
    elif folder_filter != "all":
        try:
            queryset = queryset.filter(folder_id=int(folder_filter))
        except (TypeError, ValueError):
            queryset = queryset.none()
    search = request.GET.get("q", "").strip()[:100]
    if search:
        queryset = queryset.filter(original_name__icontains=search)
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
                "folder_id": image.folder_id,
                "deletable": image.ref_count == 0 and image.lease_count == 0,
                "delete_url": reverse("mdeditor_image_delete", args=(image.pk,)),
                "move_url": reverse("mdeditor_image_move", args=(image.pk,)),
            }
        )
    folders = [
        {"id": folder.pk, "name": folder.name, "count": folder.image_count}
        for folder in EditorImageFolder.objects.annotate(
            image_count=Count("images")
        ).order_by("name", "pk")
    ]
    return JsonResponse(
        {
            "images": images,
            "folders": folders,
            "all_count": EditorImage.objects.count(),
            "uncategorized_count": EditorImage.objects.filter(
                folder__isnull=True
            ).count(),
            "page": page,
            "has_next": offset + page_size < total,
        }
    )


@require_POST
def image_folder_create(request):
    if not _can_edit(request.user):
        return JsonResponse({"detail": str(_("Permission denied."))}, status=403)
    name = _folder_name(request.POST.get("name"))
    if not name or len(name) > 100:
        return JsonResponse(
            {"detail": str(_("Enter a folder name up to 100 characters."))},
            status=400,
        )
    existing = EditorImageFolder.objects.filter(name__iexact=name).first()
    if existing:
        return JsonResponse(
            {"id": existing.pk, "name": existing.name, "created": False}
        )
    try:
        folder = EditorImageFolder.objects.create(
            name=name,
            created_by=request.user,
        )
    except IntegrityError:
        folder = EditorImageFolder.objects.get(name__iexact=name)
        return JsonResponse(
            {"id": folder.pk, "name": folder.name, "created": False}
        )
    return JsonResponse(
        {"id": folder.pk, "name": folder.name, "created": True},
        status=201,
    )


@require_POST
def image_folder_rename(request, folder_id):
    if not _can_edit(request.user):
        return JsonResponse({"detail": str(_("Permission denied."))}, status=403)
    name = _folder_name(request.POST.get("name"))
    if not name or len(name) > 100:
        return JsonResponse(
            {"detail": str(_("Enter a folder name up to 100 characters."))},
            status=400,
        )
    folder = EditorImageFolder.objects.filter(pk=folder_id).first()
    if folder is None:
        return JsonResponse({"detail": str(_("Image folder not found."))}, status=404)
    if EditorImageFolder.objects.filter(name__iexact=name).exclude(pk=folder.pk).exists():
        return JsonResponse(
            {"detail": str(_("A folder with this name already exists."))},
            status=409,
        )
    folder.name = name
    try:
        folder.save(update_fields=("name",))
    except IntegrityError:
        return JsonResponse(
            {"detail": str(_("A folder with this name already exists."))},
            status=409,
        )
    return JsonResponse({"id": folder.pk, "name": folder.name})


@require_POST
def image_folder_delete(request, folder_id):
    if not _can_edit(request.user):
        return JsonResponse({"detail": str(_("Permission denied."))}, status=403)
    folder = EditorImageFolder.objects.filter(pk=folder_id).first()
    if folder is None:
        return JsonResponse({"detail": str(_("Image folder not found."))}, status=404)
    folder.delete()
    return JsonResponse({"deleted": True})


@require_POST
def editor_image_move(request, image_id):
    if not _can_edit(request.user):
        return JsonResponse({"detail": str(_("Permission denied."))}, status=403)
    folder_id = request.POST.get("folder_id", "").strip()
    folder = None
    if folder_id:
        folder = _get_folder(folder_id)
        if folder is None:
            return JsonResponse({"detail": str(_("Image folder not found."))}, status=404)
    with transaction.atomic():
        image = EditorImage.objects.select_for_update().filter(pk=image_id).first()
        if image is None:
            return JsonResponse({"detail": str(_("Image not found."))}, status=404)
        image.folder = folder
        image.save(update_fields=("folder",))
    return JsonResponse({"moved": True, "folder_id": getattr(folder, "pk", None)})


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


@require_POST
def editor_image_abandon(request):
    if not _can_edit(request.user):
        return JsonResponse({"detail": str(_("Permission denied."))}, status=403)
    try:
        draft_id = uuid.UUID(request.POST.get("draft_id", ""))
    except (TypeError, ValueError):
        return JsonResponse({"detail": str(_("Invalid editor draft."))}, status=400)
    deleted = release_draft(request.user, draft_id)
    return JsonResponse({"deleted": deleted})
