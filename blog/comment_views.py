import logging
import hashlib
import json
import re
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.validators import URLValidator, validate_email
from django.db import transaction
from django.db.models import Count, Exists, OuterRef, Prefetch, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext as _
from PIL import Image, ImageOps, ImageSequence, UnidentifiedImageError
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt

from .services.geo import get_ip_location
from .models import (
    ArticleModel,
    Comment,
    CommentBadgeAssignment,
    CommentEmojiPack,
    CommentGifSource,
    CommentImage,
    CommentLike,
    CommentNotification,
    SiteConfiguration,
    StandalonePage,
)
from .services.client import client_info
from .services.comment_render import render_emoji, render_md
from .services.emoji import emoji_items
from .services.mail import notify
from .services.throttle import rate_limited as _rate_limited

User = get_user_model()
logger = logging.getLogger(__name__)


def _site():
    return SiteConfiguration.get_config()


def _same_origin(request):
    source = request.headers.get("Origin") or request.headers.get("Referer")
    if not source:
        return False
    parsed = urlparse(source)
    return (
        parsed.scheme.lower() == request.scheme.lower()
        and parsed.netloc.lower() == request.get_host().lower()
    )


@csrf_exempt
@require_POST
def gitalk_oauth(request):
    """Exchange Gitalk's OAuth code without exposing the client secret."""
    if not _same_origin(request):
        return JsonResponse({"error": "forbidden"}, status=403)
    if not request.content_type or request.content_type.lower() != "application/json":
        return JsonResponse({"error": "invalid_request"}, status=415)
    if len(request.body) > 4096:
        return JsonResponse({"error": "invalid_request"}, status=400)
    if _rate_limited(request, "gitalk-oauth", limit=10, period=5 * 60):
        return JsonResponse({"error": "rate_limited"}, status=429)

    site = _site()
    if not site.comment_enabled or site.comment_system != "gitalk":
        return JsonResponse({"error": "not_configured"}, status=404)
    options = site.server_comment_options()
    client_id = str(options.get("clientID") or "").strip()
    client_secret = str(options.get("clientSecret") or "").strip()
    if not client_id or not client_secret:
        return JsonResponse({"error": "not_configured"}, status=503)

    try:
        payload = json.loads(request.body)
    except (TypeError, ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "invalid_request"}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "invalid_request"}, status=400)

    code = str(payload.get("code") or "").strip()
    sent_id = str(payload.get("client_id") or "").strip()
    if sent_id != client_id or not re.fullmatch(r"[A-Za-z0-9_-]{8,255}", code):
        return JsonResponse({"error": "invalid_request"}, status=400)

    data = urlencode(
        {"client_id": client_id, "client_secret": client_secret, "code": code}
    ).encode("ascii")
    upstream = Request(
        "https://github.com/login/oauth/access_token",
        data=data,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "django-redefine-blog-gitalk",
        },
        method="POST",
    )
    try:
        with urlopen(upstream, timeout=10) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            raise ValueError("GitHub OAuth response was too large")
        result = json.loads(raw.decode("utf-8"))
    except (
        HTTPError,
        URLError,
        TimeoutError,
        ValueError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):
        logger.warning("Gitalk OAuth exchange failed", exc_info=True)
        return JsonResponse({"error": "oauth_exchange_failed"}, status=502)

    if not isinstance(result, dict):
        return JsonResponse({"error": "oauth_exchange_failed"}, status=502)
    if result.get("access_token"):
        keys = ("access_token", "scope", "token_type")
        response = JsonResponse({key: result[key] for key in keys if key in result})
    else:
        keys = ("error", "error_description", "error_uri")
        error = {key: result[key] for key in keys if key in result}
        response = JsonResponse(error or {"error": "oauth_exchange_failed"}, status=400)
    response["Cache-Control"] = "no-store"
    response["Pragma"] = "no-cache"
    response["Vary"] = "Origin"
    return response


def _comments_enabled(site, article=None, page=None):
    return bool(
        site.comment_enabled
        and site.comment_system == "internal"
        and (article is None or article.show_comment)
        and (page is None or (page.enabled and page.comments_enabled))
    )


def _target_filter(article=None, page=None):
    return {"article": article} if article is not None else {"page": page}


def _target_title(article=None, page=None):
    return article.title if article is not None else page.localized_title()


def _json_error(message, status=400):
    return JsonResponse({"ok": False, "error": message}, status=status)


def _validation_message(exc):
    """Convert Django validation dictionaries into a readable API message."""
    if isinstance(exc, ValidationError):
        messages = []
        for field, errors in exc.message_dict.items():
            labels = {
                "nickname": _("Nickname"),
                "email": _("Email"),
                "website": _("Website"),
            }
            label = labels.get(field, field)
            messages.extend(f"{label}: {error}" for error in errors)
        return "; ".join(messages) or _("The comment is invalid.")
    return str(exc)


def _comment_payload(comment, request):
    liked = getattr(comment, "viewer_liked", None)
    if liked is None:
        liked = bool(
            request.user.is_authenticated
            and CommentLike.objects.filter(comment=comment, user=request.user).exists()
        )
    site = _site()
    content_html = render_emoji(render_md(comment.content), site)
    badges = []
    if comment.author_id:
        prefetched_badges = getattr(comment.author, "visible_comment_badges", None)
        if prefetched_badges is not None:
            assignments = prefetched_badges
        else:
            assignments = CommentBadgeAssignment.objects.filter(
                user_id=comment.author_id,
                badge__enabled=True,
            ).select_related("badge")
        badges = [
            {
                "name": assignment.badge.localized_name(),
                "color": assignment.color_override or assignment.badge.color,
            }
            for assignment in assignments
        ]
    like_count = getattr(comment, "like_total", None)
    if like_count is None:
        like_count = comment.like_count
    return {
        "id": comment.id,
        "parent_id": comment.parent_id,
        "author": comment.display_name,
        "content": comment.content,
        "content_html": content_html,
        "website": (
            comment.author.profile.website
            if comment.author_id
            and hasattr(comment.author, "profile")
            and comment.author.profile.website
            else comment.website
        ),
        "avatar": comment.avatar_url,
        "verified": bool(comment.author_id),
        "badges": badges,
        "is_sticky": bool(comment.is_sticky),
        "created_at": timezone.localtime(comment.created_at).isoformat(),
        # Never expose a raw address through the public comment API. The full
        # value remains available to authorized staff in Django Admin.
        "ip_address": get_ip_location(comment.ip_address) or "",
        "browser": comment.browser,
        "operating_system": comment.operating_system,
        "like_count": like_count,
        "liked": liked,
        "can_edit": bool(
            request.user.is_authenticated and comment.author_id == request.user.id
        ),
        "can_delete": bool(
            request.user.is_authenticated
            and (
                comment.author_id == request.user.id
                or request.user.has_perm("blog.delete_comment")
            )
        ),
        "can_moderate": bool(
            request.user.is_authenticated
            and request.user.has_perm("blog.change_comment")
        ),
    }


@require_GET
def comments(request, slug):
    article = get_object_or_404(ArticleModel.objects.published(), slug=slug)
    return _target_comments(request, article=article)


@require_GET
def page_comments(request, slug):
    page = get_object_or_404(
        StandalonePage,
        config=_site(),
        page_type=StandalonePage.CUSTOM,
        slug=slug,
        enabled=True,
        comments_enabled=True,
    )
    return _target_comments(request, page=page)


def _target_comments(request, article=None, page=None):
    site = _site()
    if not _comments_enabled(site, article=article, page=page):
        return _json_error(_("Comments are disabled for this page."), 403)
    from .signals import grant_owner_badge

    target_filter = _target_filter(article=article, page=page)
    for owner in User.objects.filter(
        is_superuser=True,
        **{f"blog_comments__{key}": value for key, value in target_filter.items()},
    ).distinct():
        grant_owner_badge(owner, site)

    badge_prefetch = Prefetch(
        "author__comment_badges",
        queryset=CommentBadgeAssignment.objects.filter(badge__enabled=True)
        .select_related("badge")
        .prefetch_related("badge__translations"),
        to_attr="visible_comment_badges",
    )
    qs = (
        Comment.objects.filter(is_approved=True, **target_filter)
        .select_related("author", "author__profile")
        .prefetch_related(badge_prefetch)
        .annotate(like_total=Count("likes"))
        .order_by("-is_sticky", "-created_at")
    )
    if request.user.is_authenticated:
        qs = qs.annotate(
            viewer_liked=Exists(
                CommentLike.objects.filter(comment_id=OuterRef("pk"), user=request.user)
            )
        )
    comments = [_comment_payload(item, request) for item in qs]
    return JsonResponse({"ok": True, "comments": comments})


@require_POST
def comment_preview(request):
    """render the composer preview through the same pipeline used after posting."""
    if not _comments_enabled(_site()):
        return _json_error(_("Internal comments are disabled."), 403)
    if _rate_limited(request, "preview", limit=180, period=60):
        return _json_error(_("Too many preview requests. Please try again later."), 429)

    content = request.POST.get("content") or ""
    if len(content) > 5000:
        return _json_error(_("Comment length must not exceed 5000 characters."))
    site = _site()
    return JsonResponse({"ok": True, "html": render_emoji(render_md(content), site)})


def _has_image(content, upload):
    image_url = upload.image.url
    image_path = urlparse(image_url).path
    return image_url in content or bool(image_path and image_path in content)


def _sync_images(comment, uploader, upload_ids=()):
    """Attach referenced uploads and remove files discarded by an edit."""
    content = comment.content or ""
    for upload in comment.images.all():
        if not _has_image(content, upload):
            upload.delete()
    if uploader is None:
        return
    candidate_ids = {str(value) for value in upload_ids if str(value).isdigit()}
    candidates = CommentImage.objects.filter(
        uploader=uploader,
        comment__isnull=True,
        created_at__gte=timezone.now() - timedelta(days=1),
    )
    for upload in candidates:
        if (not candidate_ids or str(upload.pk) in candidate_ids) and _has_image(
            content, upload
        ):
            upload.comment = comment
            upload.save(update_fields=("comment",))


@require_POST
def create_comment(request, slug):
    article = get_object_or_404(ArticleModel.objects.published(), slug=slug)
    return _create_comment(request, article=article)


@require_POST
def create_page_comment(request, slug):
    page = get_object_or_404(
        StandalonePage,
        config=_site(),
        page_type=StandalonePage.CUSTOM,
        slug=slug,
        enabled=True,
        comments_enabled=True,
    )
    return _create_comment(request, page=page)


def _create_comment(request, article=None, page=None):
    site = _site()
    if site.comment_require_login and not request.user.is_authenticated:
        return _json_error(_("Please sign in to comment."), 401)
    if not request.user.is_authenticated and not site.comment_allow_guest:
        return _json_error(_("Guest comments are disabled."), 403)
    content = (request.POST.get("content") or "").strip()
    if not content or len(content) > 5000:
        return _json_error(_("Comment length must be between 1 and 5000 characters."))
    if _rate_limited(request, "create"):
        return _json_error(_("Too many comments. Please try again later."), 429)

    if not _comments_enabled(site, article=article, page=page):
        return _json_error(_("Comments are disabled for this page."), 403)
    target_filter = _target_filter(article=article, page=page)
    parent = None
    parent_id = request.POST.get("parent_id")
    if parent_id:
        parent = get_object_or_404(
            Comment, pk=parent_id, is_approved=True, **target_filter
        )

    nickname = (request.POST.get("nickname") or "").strip()[:80]
    email = (request.POST.get("email") or "").strip()[:254]
    website = (request.POST.get("website") or "").strip()[:200]
    if request.user.is_authenticated:
        profile = getattr(request.user, "profile", None)
        website = (profile.website if profile else "")[:200]
    if not request.user.is_authenticated:
        if email:
            try:
                validate_email(email)
            except ValidationError:
                return _json_error(_("Enter a valid email address."))
        if website:
            try:
                URLValidator()(website)
            except ValidationError:
                return _json_error(_("Enter a valid website URL."))

    ip_address, browser, operating_system = client_info(request)
    comment = Comment(
        article=article,
        page=page,
        parent=parent,
        author=request.user if request.user.is_authenticated else None,
        nickname=nickname,
        email=email,
        website=website,
        content=content,
        ip_address=ip_address,
        browser=browser,
        operating_system=operating_system,
        is_approved=site.comment_auto_approve,
    )
    try:
        # validate contact fields only when supplied, so guest email and website
        # remain optional while every other model rule still runs
        comment.full_clean(exclude=("email", "website"))
    except ValidationError as exc:
        return _json_error(_validation_message(exc))
    comment.save()
    _sync_images(
        comment,
        request.user if request.user.is_authenticated else None,
        request.POST.getlist("image_ids"),
    )

    if comment.is_approved and parent and parent.author_id:
        notify(
            parent.author,
            request.user if request.user.is_authenticated else None,
            comment,
            CommentNotification.REPLY,
            "Someone replied to your comment",
            f"{comment.display_name} replied to your comment on {_target_title(article, page)}.",
        )
    if not comment.is_approved:
        return JsonResponse({"ok": True, "pending": True})
    return JsonResponse({"ok": True, "comment": _comment_payload(comment, request)})


@require_POST
def toggle_like(request, comment_id):
    if not request.user.is_authenticated:
        return _json_error(_("Please sign in to like comments."), 401)
    site = _site()
    if not site.comment_allow_likes:
        return _json_error(_("Comment likes are disabled."), 403)
    if _rate_limited(request, "like", limit=60):
        return _json_error(_("Too many requests."), 429)
    comment = get_object_or_404(
        Comment.objects.filter(
            Q(article__is_published=True, article__created_at__lte=timezone.now())
            | Q(page__enabled=True, page__comments_enabled=True)
        ),
        pk=comment_id,
        is_approved=True,
    )
    like, created = CommentLike.objects.get_or_create(
        comment=comment, user=request.user
    )
    if not created:
        like.delete()
    elif comment.author_id:
        target_title = _target_title(comment.article, comment.page)
        message = (
            f"{request.user.get_username()} liked your comment on " f"{target_title}."
        )
        notify(
            comment.author,
            request.user,
            comment,
            CommentNotification.LIKE,
            "Someone liked your comment",
            message,
        )
    return JsonResponse(
        {"ok": True, "liked": created, "like_count": comment.like_count}
    )


@require_POST
def edit_comment(request, comment_id):
    if not request.user.is_authenticated:
        return _json_error(_("Please sign in to edit comments."), 401)
    comment = get_object_or_404(Comment, pk=comment_id)
    if comment.author_id != request.user.id:
        return _json_error(_("You cannot edit this comment."), 403)
    content = (request.POST.get("content") or "").strip()
    if not content or len(content) > 5000:
        return _json_error(_("Comment length must be between 1 and 5000 characters."))
    comment.content = content
    comment.save(update_fields=("content", "updated_at"))
    _sync_images(comment, request.user, request.POST.getlist("image_ids"))
    return JsonResponse({"ok": True, "comment": _comment_payload(comment, request)})


@require_POST
def delete_comment(request, comment_id):
    if not request.user.is_authenticated:
        return _json_error(_("Please sign in to delete comments."), 401)
    comment = get_object_or_404(Comment, pk=comment_id)
    if not (
        comment.author_id == request.user.id
        or request.user.has_perm("blog.delete_comment")
    ):
        return _json_error(_("You cannot delete this comment."), 403)
    comment.delete()
    return JsonResponse({"ok": True, "deleted": comment_id})


@require_POST
def toggle_sticky(request, comment_id):
    if not request.user.has_perm("blog.change_comment"):
        return _json_error(_("Only administrators can pin comments."), 403)
    with transaction.atomic():
        comment = get_object_or_404(Comment.objects.select_for_update(), pk=comment_id)
        target_filter = _target_filter(comment.article, comment.page)
        if (
            not comment.is_sticky
            and Comment.objects.filter(is_sticky=True, **target_filter)
            .exclude(pk=comment.pk)
            .exists()
        ):
            return _json_error(_("Only one comment can be pinned at a time."), 409)
        comment.is_sticky = not comment.is_sticky
        comment.save(update_fields=("is_sticky", "updated_at"))
    return JsonResponse({"ok": True, "is_sticky": comment.is_sticky})


@require_GET
def notifications(request):
    if not request.user.is_authenticated:
        return _json_error(_("Please sign in to view notifications."), 401)
    items = CommentNotification.objects.filter(recipient=request.user).select_related(
        "actor", "comment"
    )[:50]
    return JsonResponse(
        {
            "ok": True,
            "unread": CommentNotification.objects.filter(
                recipient=request.user, is_read=False
            ).count(),
            "notifications": [
                {
                    "id": item.id,
                    "kind": item.kind,
                    "read": item.is_read,
                    "actor": item.actor.get_username() if item.actor else "Someone",
                    "comment_id": item.comment_id,
                    "created_at": timezone.localtime(item.created_at).isoformat(),
                }
                for item in items
            ],
        }
    )


@require_POST
def mark_notifications_read(request):
    if not request.user.is_authenticated:
        return _json_error(_("Please sign in to manage notifications."), 401)
    CommentNotification.objects.filter(recipient=request.user, is_read=False).update(
        is_read=True
    )
    return JsonResponse({"ok": True})


@require_GET
def comment_assets(request):
    site = _site()
    packs = []
    if site.comment_emoji_enabled:
        pack_rows = CommentEmojiPack.objects.filter(
            config=site,
            enabled=True,
        ).prefetch_related("items")
        for pack in pack_rows:
            items = emoji_items(pack)
            packs.append(
                {
                    "name": pack.name,
                    "icon": items[0]["url"] if items else "",
                    "items": items,
                }
            )
    gifs = []
    if site.comment_gif_enabled:
        gifs = []
        for source in CommentGifSource.objects.filter(config=site, enabled=True):
            endpoint = source.endpoint
            if urlparse(endpoint).netloc.lower() == "api.giphy.com":
                # keep the provider key server-side, so the browser sees only
                # a source identifier for the same-origin proxy
                endpoint = f"/api/comment-gif-proxy/?source={source.pk}"
            gifs.append({"name": source.name, "endpoint": endpoint})
    return JsonResponse({"ok": True, "emoji": packs, "gif": gifs})


@require_GET
def comment_gif_proxy(request):
    """Proxy configured GIF search providers to avoid browser CORS failures."""
    site = _site()
    source_id = request.GET.get("source")
    source = CommentGifSource.objects.filter(
        config=site, enabled=True, pk=source_id
    ).first()
    target = str(source.endpoint if source else "").strip()
    if _rate_limited(request, "gif", limit=30, period=60):
        return _json_error(_("Too many GIF searches. Please try again later."), 429)
    parsed = urlparse(target)
    allowed_paths = {"/v1/gifs/search", "/v1/gifs/trending"}
    if (
        parsed.scheme != "https"
        or parsed.netloc.lower() != "api.giphy.com"
        or parsed.path.rstrip("/") not in allowed_paths
    ):
        return _json_error(_("Unsupported GIF provider."), 400)
    try:
        query = parse_qs(parsed.query)
        term = str(request.GET.get("q", query.get("q", [""])[0])).strip()[:100]
        if term:
            parsed_path = "/v1/gifs/search"
            query["q"] = [term]
        else:
            parsed_path = "/v1/gifs/trending"
            query.pop("q", None)
        # bound provider requests despite configured query values, so one search
        # cannot consume excessive upstream bandwidth or render work
        try:
            limit = max(1, min(int(query.get("limit", [30])[0]), 50))
        except (TypeError, ValueError):
            limit = 30
        query["limit"] = [str(limit)]
        query_string = urlencode({key: value[0] for key, value in query.items()})
        upstream = Request(
            "https://api.giphy.com" + parsed_path + "?" + query_string,
            headers={"Accept": "application/json", "User-Agent": "DjangoRedefine/1.0"},
        )
        with urlopen(upstream, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        logger.warning("Unable to query configured Giphy source", exc_info=True)
        return JsonResponse({"results": []})
    return JsonResponse({"results": payload.get("data", [])})


@require_POST
def comment_upload(request):
    if not request.user.is_authenticated:
        return _json_error(_("Please sign in to upload images."), 401)
    if not _comments_enabled(_site()):
        return _json_error(_("Internal comment uploads are disabled."), 403)
    if _rate_limited(request, "upload", limit=10, period=60 * 60):
        return _json_error(_("Too many image uploads. Please try again later."), 429)
    upload = request.FILES.get("image")
    max_bytes = settings.COMMENT_UPLOAD_MAX_BYTES
    if not upload or upload.size > max_bytes:
        size_mb = max_bytes // (1024 * 1024)
        return _json_error(
            _("Image must be smaller than %(size)s MB.") % {"size": size_mb}
        )
    allowed = {"image/jpeg", "image/png", "image/gif", "image/webp"}
    if upload.content_type not in allowed:
        return _json_error(_("Unsupported image type."))
    # validate file bytes before storage, because browser MIME types and names
    # are client-controlled and cannot prove that a file is an image
    expected_formats = {
        "image/jpeg": {"JPEG"},
        "image/png": {"PNG"},
        "image/gif": {"GIF"},
        "image/webp": {"WEBP"},
    }
    try:
        upload.seek(0)
        with Image.open(upload) as image:
            image.verify()
            detected_format = image.format
        upload.seek(0)
        with Image.open(upload) as image:
            width, height = image.size
            frames = getattr(image, "n_frames", 1)
        upload.seek(0)
    except (UnidentifiedImageError, OSError, ValueError):
        return _json_error(_("Image data is invalid."))
    if detected_format not in expected_formats[upload.content_type]:
        return _json_error(_("Image data does not match its declared type."))
    if max(width, height) > settings.COMMENT_UPLOAD_MAX_DIMENSION:
        return _json_error(_("Image dimensions are too large."))
    if width * height * frames > settings.COMMENT_UPLOAD_MAX_PIXELS:
        return _json_error(_("Image contains too many pixels or animation frames."))
    # derive the suffix from the accepted MIME type, so misleading client
    # extensions cannot create executable-looking filenames
    extensions = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/gif": "gif",
        "image/webp": "webp",
    }
    extension = extensions[upload.content_type]
    upload.seek(0)
    digest = hashlib.sha256()
    with Image.open(upload) as image:
        digest.update(
            f"{image.size[0]}x{image.size[1]}:{getattr(image, 'n_frames', 1)}".encode()
        )
        for frame in ImageSequence.Iterator(image):
            normalized = ImageOps.exif_transpose(frame).convert("RGBA")
            digest.update(normalized.tobytes())
            digest.update(str(frame.info.get("duration", 0)).encode())
    content_hash = digest.hexdigest()
    upload.seek(0)
    existing_path = (
        CommentImage.objects.filter(content_hash=content_hash)
        .exclude(image="")
        .values_list("image", flat=True)
        .first()
    )
    path = existing_path or f"comment-images/{content_hash}.{extension}"
    # remove abandoned uploads opportunistically, so cancelled comments cannot
    # accumulate files forever even when no scheduled cleanup job is installed
    CommentImage.objects.filter(
        comment__isnull=True,
        created_at__lt=timezone.now() - timedelta(days=1),
    ).delete()
    try:
        if default_storage.exists(path):
            saved = path
        else:
            saved = default_storage.save(path, upload)
            # A storage backend may resolve a simultaneous name collision by
            # returning a suffixed name. The digest path is already the same
            # content, so discard that racing copy and share the canonical
            # object instead.
            if saved != path and default_storage.exists(path):
                default_storage.delete(saved)
                saved = path
        try:
            image = CommentImage.objects.filter(
                uploader=request.user,
                comment__isnull=True,
                content_hash=content_hash,
            ).first()
            if image is None:
                image = CommentImage.objects.create(
                    uploader=request.user,
                    image=saved,
                    content_hash=content_hash,
                )
        except Exception:
            if not CommentImage.objects.filter(image=saved).exists():
                default_storage.delete(saved)
            raise
    except Exception:
        logger.exception("Failed to save comment image upload")
        return _json_error(_("Image upload failed. Please try again later."), 500)
    return JsonResponse({"ok": True, "url": image.image.url, "image_id": image.pk})
