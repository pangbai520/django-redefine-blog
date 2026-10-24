import logging
import json
import re
import uuid
from datetime import timedelta
from html import unescape
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.views import PasswordResetView
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives, send_mail
from django.core.files.storage import default_storage
from django.core.validators import URLValidator, validate_email
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import url_has_allowed_host_and_scheme, urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.html import escape
from django.utils.translation import gettext as _
from markdown import Markdown
from PIL import Image, UnidentifiedImageError
from django.views.decorators.http import require_GET, require_POST

from core.markdown.blocks.code_block import render_highlighted_code

from .forms import CommentRegistrationForm
from .middleware import get_client_ip
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
)


User = get_user_model()
logger = logging.getLogger(__name__)


class RateLimitedPasswordResetView(PasswordResetView):
    """Apply the same abuse controls to password mail as other account mail."""

    def post(self, request, *args, **kwargs):
        if _rate_limited(request, "password-reset", limit=5, period=60 * 60):
            form = self.get_form()
            form.add_error(None, _("Too many password reset requests. Please try again later."))
            return self.render_to_response(self.get_context_data(form=form), status=429)
        return super().post(request, *args, **kwargs)


class _CommentHTMLSanitizer(HTMLParser):
    """Keep the small safe HTML subset used by Waline comments."""

    allowed_tags = {"p", "br", "hr", "strong", "b", "em", "i", "del", "s", "code", "pre", "blockquote", "ul", "ol", "li", "a", "img", "font", "span"}
    void_tags = {"br", "hr", "img"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.output = []
        self.blocked = 0

    @staticmethod
    def _safe_url(value):
        value = (value or "").strip()
        parsed = urlparse(value)
        if (value.startswith("/") and not value.startswith("//")) or (
            parsed.scheme.lower() in {"http", "https"} and bool(parsed.netloc)
        ):
            return value
        return ""

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in {"script", "style"}:
            self.blocked += 1
            return
        if self.blocked or tag not in self.allowed_tags:
            return
        attrs = dict(attrs)
        safe_attrs = []
        if tag == "a":
            href = self._safe_url(attrs.get("href"))
            if href:
                safe_attrs.append(("href", href))
                safe_attrs.extend((("target", "_blank"), ("rel", "nofollow noopener noreferrer")))
        elif tag == "img":
            src = self._safe_url(attrs.get("src"))
            if not src:
                return
            safe_attrs.append(("src", src))
            if attrs.get("alt"):
                safe_attrs.append(("alt", attrs["alt"][:120]))
            # add Waline's class only to known emoji assets, so uploaded and
            # user-provided images keep ordinary content sizing
            alt = (attrs.get("alt") or "").strip().lower()
            source_class = (attrs.get("class") or "").split()
            if "wl-emoji" in source_class or re.match(r"^(?:bmoji|tieba)_", alt):
                safe_attrs.append(("class", "wl-emoji"))
            else:
                safe_attrs.append(("class", "internal-comment-image"))
        elif tag == "font":
            color = (attrs.get("color") or "").strip()
            if re.fullmatch(r"(?:#[0-9a-f]{3,8}|[a-z]{1,32}|rgb\([0-9%,.\s]+\))", color, re.I):
                safe_attrs.append(("color", color))
        elif tag == "code":
            classes = [
                item for item in (attrs.get("class") or "").split()
                if item == "hljs" or re.fullmatch(r"language-[\w+-]+", item)
            ]
            if classes:
                safe_attrs.append(("class", " ".join(classes)))
        elif tag == "span":
            classes = [
                item for item in (attrs.get("class") or "").split()
                if re.fullmatch(r"hljs-[a-z_]+", item) or item in {"function_", "class_"}
            ]
            if classes:
                safe_attrs.append(("class", " ".join(classes)))
        self.output.append("<" + tag + "".join(f' {key}="{escape(value)}"' for key, value in safe_attrs) + ">")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"script", "style"}:
            self.blocked = max(0, self.blocked - 1)
        elif not self.blocked and tag in self.allowed_tags and tag not in self.void_tags:
            self.output.append(f"</{tag}>")

    def handle_data(self, data):
        if not self.blocked:
            self.output.append(escape(data))


def _sanitize_comment_html(value):
    parser = _CommentHTMLSanitizer()
    parser.feed(value or "")
    parser.close()
    return "".join(parser.output)


def _client_details(request):
    """Extract the compact client labels shown on a Waline comment card."""
    user_agent = request.META.get("HTTP_USER_AGENT", "")
    browser = "Unknown browser"
    browser_patterns = (
        (r"Edg/([\d.]+)", "Edge"),
        (r"OPR/([\d.]+)", "Opera"),
        (r"Chrome/([\d.]+)", "Chrome"),
        (r"Firefox/([\d.]+)", "Firefox"),
        (r"Version/([\d.]+).*Safari/", "Safari"),
    )
    for pattern, label in browser_patterns:
        match = re.search(pattern, user_agent)
        if match:
            browser = f"{label}{match.group(1)}"
            break

    operating_system = "Unknown OS"
    windows = re.search(r"Windows NT ([\d.]+)", user_agent)
    android = re.search(r"Android ([\d.]+)", user_agent)
    iphone = re.search(r"iPhone OS ([\d_]+)", user_agent)
    macos = re.search(r"Mac OS X ([\d_]+)", user_agent)
    if windows:
        windows_versions = {"10.0": "Windows 10", "6.3": "Windows 8.1", "6.2": "Windows 8", "6.1": "Windows 7"}
        operating_system = windows_versions.get(windows.group(1), f"Windows {windows.group(1)}")
        client_hint = request.META.get("HTTP_SEC_CH_UA_PLATFORM_VERSION", "").strip('" ')
        if client_hint:
            try:
                if int(client_hint.split(".", 1)[0]) >= 13:
                    operating_system = "Windows 11"
            except ValueError:
                pass
    elif android:
        operating_system = f"Android {android.group(1)}"
    elif iphone:
        operating_system = f"iOS {iphone.group(1).replace('_', '.')}"
    elif macos:
        operating_system = f"macOS {macos.group(1).replace('_', '.')}"
    elif "Linux" in user_agent:
        operating_system = "Linux"

    return get_client_ip(request), browser, operating_system


def _render_comment_markdown(content):
    """Render the small Markdown subset allowed in comments."""
    source = content or ""
    # allow useful Markdown while flattening headings, so comments cannot
    # compete with the article's document structure
    source = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", source)
    html = Markdown(extensions=["extra", "nl2br"], output_format="html5").convert(source)
    html = re.sub(
        r'<pre><code(?: class="language-(?P<language>[\w+-]+)")?>(?P<code>[\s\S]*?)</code></pre>',
        _render_comment_code_block,
        html,
    )
    return _sanitize_comment_html(html)


def _render_comment_code_block(match):
    """highlight fenced comment code before the final HTML safety pass."""
    language = (match.group("language") or "text").lower()
    raw_code = unescape(match.group("code"))
    highlighted = render_highlighted_code(raw_code, language)
    return f'<pre><code class="hljs language-{language}">{highlighted}</code></pre>'


def _site():
    return SiteConfiguration.get_config()


def _internal_comments_available(site, article=None):
    return bool(
        site.comment_enabled
        and site.comment_system == "internal"
        and (article is None or article.show_comment)
    )


def _emoji_pack_items(pack):
    """Return configured emoji rows, discovering image files from base_url when empty."""
    items = [{"name": item.name, "url": item.image_url} for item in pack.items.all()]
    if items or not pack.base_url:
        return items
    base = pack.base_url.rstrip("/")
    cache_key = f"comment-emoji-pack:{pack.pk}:{base}"
    cached = cache.get(cache_key)
    if cached is not None:
        # discard entries from the older path-joining bug, so duplicate pack names do not return
        duplicate_prefix = "/" + base.rsplit("/", 1)[-1].lower() + "/"
        if all(
            str(item.get("url", "")).startswith(base + "/")
            and duplicate_prefix not in str(item.get("url", "")).lower().replace(base.lower(), "", 1)
            for item in cached
        ):
            return cached
    discovered = []
    try:
        raw = ""
        # prefer Waline's info.json manifest, because it preserves the exact
        # item order, prefix and extension before any directory-listing fallback
        try:
            manifest_request = Request(base + "/info.json", headers={"User-Agent": "DjangoRedefineBlog/1.0"})
            with urlopen(manifest_request, timeout=4) as response:
                manifest = json.loads(response.read().decode("utf-8"))
            prefix = str(manifest.get("prefix", ""))
            extension = str(manifest.get("type", "")).lstrip(".")
            manifest_items = manifest.get("items", [])
            if isinstance(manifest_items, list) and manifest_items:
                for entry in manifest_items:
                    value = str(entry.get("name", entry.get("id", "")) if isinstance(entry, dict) else entry).strip()
                    if not value:
                        continue
                    filename = value
                    if prefix and not filename.startswith(prefix):
                        filename = prefix + filename
                    if extension and not re.search(r"\.[a-z0-9]{2,5}$", filename, re.I):
                        filename += "." + extension
                    image_url = base + "/" + filename
                    name = filename.rsplit("/", 1)[-1].rsplit(".", 1)[0]
                    discovered.append({"name": name, "url": image_url})
                if discovered:
                    cache.set(cache_key, discovered, 604800)
                    return discovered
        except Exception:
            pass
        for listing_url in (base + "/?meta", base + "/"):
            try:
                request = Request(listing_url, headers={"User-Agent": "DjangoRedefineBlog/1.0"})
                with urlopen(request, timeout=4) as response:
                    raw = response.read().decode("utf-8")
                if raw:
                    break
            except Exception:
                continue
        if not raw:
            raise ValueError("empty emoji directory response")
        try:
            payload = json.loads(raw)
            entries = payload.get("files", payload.get("entries", payload if isinstance(payload, list) else []))
            links = [entry.get("path", entry.get("url", "")) if isinstance(entry, dict) else str(entry) for entry in entries]
        except (TypeError, ValueError):
            # ignore HTML directory listings, so provider error pages never become fake packs
            links = re.findall(r'href=["\']([^"\']+\.(?:png|jpe?g|gif|webp))["\']', raw, re.I)
        for link in links:
            if not re.search(r"\.(?:png|jpe?g|gif|webp)$", link, re.I):
                continue
            base_name = base.rsplit("/", 1)[-1]
            raw_link = str(link).strip()
            if re.match(r"^https?://", raw_link, re.I):
                image_url = raw_link
            else:
                path = raw_link.lstrip("/")
                if path.lower().startswith(base_name.lower() + "/"):
                    path = path[len(base_name) + 1:]
                base_path = urlparse(base).path.strip("/")
                if path.lower().startswith(base_path.lower() + "/"):
                    image_url = urlparse(base).scheme + "://" + urlparse(base).netloc + "/" + path
                else:
                    image_url = base + "/" + path
            name = image_url.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            discovered.append({"name": name, "url": image_url})
    except Exception:
        logger.warning("Unable to discover emoji pack %s", pack.name, exc_info=True)
    cache.set(cache_key, discovered, 604800)
    return discovered


def _safe_next(request, candidate):
    if candidate and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return candidate
    return "/"


def _json_error(message, status=400):
    return JsonResponse({"ok": False, "error": message}, status=status)


def _validation_message(exc):
    """Convert Django validation dictionaries into a readable API message."""
    if isinstance(exc, ValidationError):
        messages = []
        for field, errors in exc.message_dict.items():
            label = {"nickname": _("Nickname"), "email": _("Email"), "website": _("Website")}.get(field, field)
            messages.extend(f"{label}: {error}" for error in errors)
        return "; ".join(messages) or _("The comment is invalid.")
    return str(exc)


def _comment_payload(comment, request):
    liked = bool(
        request.user.is_authenticated
        and CommentLike.objects.filter(comment=comment, user=request.user).exists()
    )
    content_html = _render_comment_markdown(comment.content)
    site = _site()
    if site.comment_emoji_enabled:
        for pack in CommentEmojiPack.objects.filter(config=site, enabled=True).prefetch_related("items"):
            for item in _emoji_pack_items(pack):
                token = escape(f":{item['name']}:")
                image = f'<img class="wl-emoji internal-comment-emoji" src="{escape(item["url"])}" alt="{escape(item["name"])}">'
                content_html = content_html.replace(token, image)
    badges = []
    if comment.author_id:
        badges = [
            {"name": assignment.badge.name, "color": assignment.color_override or assignment.badge.color}
            for assignment in CommentBadgeAssignment.objects.filter(
                user_id=comment.author_id,
                badge__enabled=True,
            ).select_related("badge")
        ]
    return {
        "id": comment.id,
        "parent_id": comment.parent_id,
        "author": comment.display_name,
        "content": comment.content,
        "content_html": content_html,
        "website": comment.website,
        "avatar": comment.avatar_url,
        "verified": bool(comment.author_id),
        "badges": badges,
        "is_sticky": bool(comment.is_sticky),
        "created_at": timezone.localtime(comment.created_at).isoformat(),
        "ip_address": comment.ip_address or "",
        "browser": comment.browser,
        "operating_system": comment.operating_system,
        "like_count": comment.like_count,
        "liked": liked,
        "can_edit": bool(request.user.is_authenticated and comment.author_id == request.user.id),
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


def _notify(recipient, actor, comment, kind, subject, body):
    if not recipient or recipient == actor:
        return
    notification, created = CommentNotification.objects.get_or_create(
        recipient=recipient,
        actor=actor,
        comment=comment,
        kind=kind,
    )
    site = _site()
    if created and site.comment_email_notifications and recipient.email:
        try:
            send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [recipient.email])
        except Exception:
            # keep notification state even when SMTP fails, so delivery outages do not lose events
            logger.exception("Failed to send comment notification to %s", recipient.email)


def _send_verification_email(request, user):
    """Send one activation link and report delivery failures to the caller."""
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    verify_url = request.build_absolute_uri(
        reverse("comment_verify", kwargs={"uidb64": uid, "token": token})
    )
    message = EmailMultiAlternatives(
        "Verify your comment account",
        f"Open this link to activate your account:\n\n{verify_url}",
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
    )
    message.attach_alternative(
        render_to_string(
            "emails/verify_account.html",
            {"verify_url": verify_url},
            request=request,
        ),
        "text/html",
    )
    if message.send() != 1:
        raise RuntimeError("The verification email was not accepted by the mail backend.")


def _create_registered_user(request, form, site):
    """Create an account, removing it again when required mail cannot be delivered."""
    user = User.objects.create_user(
        username=form.cleaned_data["username"],
        email=form.cleaned_data["email"],
        password=form.cleaned_data["password"],
        is_active=not site.comment_require_email_verification,
    )
    if not site.comment_require_email_verification:
        return user
    try:
        _send_verification_email(request, user)
    except Exception:
        # do not leave an unusable account reserving the submitted name or email
        user.delete()
        raise
    return user


def register(request):
    site = _site()
    if not site.comment_registration_enabled:
        return _json_error(_("Registration is disabled."), 403) if request.headers.get("Accept") == "application/json" else render(
            request, "comments/register.html", {"form": None, "registration_disabled": True}
        )

    if request.method == "POST":
        form = CommentRegistrationForm(request.POST)
        if _rate_limited(request, "register", limit=5, period=60 * 60):
            form.add_error(None, _("Too many registration attempts. Please try again later."))
            return render(request, "comments/register.html", {"form": form}, status=429)
        if form.is_valid():
            try:
                user = _create_registered_user(request, form, site)
            except Exception:
                logger.exception(
                    "Failed to complete account registration for %s",
                    form.cleaned_data["email"],
                )
                return render(
                    request,
                    "comments/register_done.html",
                    {"email": form.cleaned_data["email"], "mail_error": True},
                    status=502,
                )
            if site.comment_require_email_verification:
                return render(request, "comments/register_done.html", {"email": user.email})
            login(
                request,
                user,
                backend="django.contrib.auth.backends.ModelBackend",
            )
            return redirect(_safe_next(request, request.POST.get("next")))
    else:
        form = CommentRegistrationForm()
    return render(request, "comments/register.html", {"form": form})


def verify(request, uidb64, token):
    try:
        user = User.objects.get(pk=force_str(urlsafe_base64_decode(uidb64)))
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None
    if user and default_token_generator.check_token(user, token):
        user.is_active = True
        user.save(update_fields=("is_active",))
        login(
            request,
            user,
            backend="django.contrib.auth.backends.ModelBackend",
        )
        return render(request, "comments/verify_done.html", {"verified": True})
    return render(request, "comments/verify_done.html", {"verified": False}, status=400)


def login_view(request):
    login_limited = False
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if _rate_limited(request, "login", limit=10, period=15 * 60):
            login_limited = True
            form.add_error(None, _("Too many sign-in attempts. Please try again later."))
        elif form.is_valid():
            login(request, form.get_user())
            if request.GET.get("modal") == "1":
                return render(request, "comments/login_modal_done.html")
            return redirect(_safe_next(request, request.POST.get("next") or request.GET.get("next")))
    else:
        form = AuthenticationForm(request)
    if request.method == "POST" and not login_limited and not form.is_valid():
        username = request.POST.get("username", "").strip()
        pending_user = User.objects.filter(username=username, is_active=False).first()
        if pending_user:
            form.add_error(None, _("We sent a verification email to your registered address. Please verify your email before signing in."))
    template = "comments/login_modal.html" if request.GET.get("modal") == "1" else "comments/login.html"
    return render(request, template, {"form": form})


@require_POST
def login_ajax(request):
    if _rate_limited(request, "login", limit=10, period=15 * 60):
        return _json_error(_("Too many sign-in attempts. Please try again later."), 429)
    username = request.POST.get("username", "")
    password = request.POST.get("password", "")
    user = authenticate(request, username=username, password=password)
    if user is None:
        pending = User.objects.filter(username=username, is_active=False).exists()
        return _json_error(
            "We sent a verification email to your registered address. Please verify your email before signing in." if pending else "Invalid username or password.",
            401,
        )
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return JsonResponse({"ok": True, "username": user.get_username()})


@require_POST
def register_ajax(request):
    site = _site()
    if not site.comment_registration_enabled:
        return _json_error(_("Registration is disabled."), 403)
    if _rate_limited(request, "register", limit=5, period=60 * 60):
        return _json_error(_("Too many registration attempts. Please try again later."), 429)
    form = CommentRegistrationForm(request.POST)
    if not form.is_valid():
        return _json_error(" ".join(str(error) for errors in form.errors.values() for error in errors))
    try:
        user = _create_registered_user(request, form, site)
    except Exception:
        logger.exception(
            "Failed to complete account registration for %s",
            form.cleaned_data["email"],
        )
        return _json_error(_("Registration failed because the verification email could not be sent."), 502)
    if site.comment_require_email_verification:
        return JsonResponse({"ok": True, "pending": True})
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return JsonResponse({"ok": True, "pending": False})


@require_POST
def logout_view(request):
    next_url = _safe_next(request, request.POST.get("next"))
    logout(request)
    return redirect(next_url)


@require_GET
def comments(request, slug):
    article = get_object_or_404(ArticleModel.objects.published(), slug=slug)
    if not _internal_comments_available(_site(), article):
        return _json_error(_("Comments are disabled for this article."), 403)
    qs = Comment.objects.filter(article=article, is_approved=True).select_related("author").order_by("-is_sticky", "-created_at")
    comments = [_comment_payload(item, request) for item in qs]
    return JsonResponse({"ok": True, "comments": comments})


def _rate_limited(request, action, limit=10, period=60):
    ident = request.user.pk if request.user.is_authenticated else get_client_ip(request) or "unknown"
    key = f"comment:{action}:{ident}"
    if cache.add(key, 1, period):
        return False
    try:
        return cache.incr(key) > limit
    except ValueError:
        cache.set(key, 1, period)
        return False


@require_POST
def comment_preview(request):
    """render the composer preview through the same pipeline used after posting."""
    if not _internal_comments_available(_site()):
        return _json_error(_("Internal comments are disabled."), 403)
    if _rate_limited(request, "preview", limit=180, period=60):
        return _json_error(_("Too many preview requests. Please try again later."), 429)

    content = request.POST.get("content") or ""
    if len(content) > 5000:
        return _json_error(_("Comment length must not exceed 5000 characters."))
    return JsonResponse({"ok": True, "html": _render_comment_markdown(content)})


def _sync_comment_images(comment, uploader):
    """Attach referenced uploads and remove files discarded by an edit."""
    content = comment.content or ""
    for upload in comment.images.all():
        if upload.image.url not in content:
            upload.delete()
    if uploader is None:
        return
    candidates = CommentImage.objects.filter(
        uploader=uploader,
        comment__isnull=True,
        created_at__gte=timezone.now() - timedelta(days=1),
    )
    for upload in candidates:
        if upload.image.url in content:
            upload.comment = comment
            upload.save(update_fields=("comment",))


@require_POST
def create_comment(request, slug):
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

    article = get_object_or_404(ArticleModel.objects.published(), slug=slug)
    if not _internal_comments_available(site, article):
        return _json_error(_("Comments are disabled for this article."), 403)
    parent = None
    parent_id = request.POST.get("parent_id")
    if parent_id:
        parent = get_object_or_404(Comment, pk=parent_id, article=article, is_approved=True)

    nickname = (request.POST.get("nickname") or "").strip()[:80]
    email = (request.POST.get("email") or "").strip()[:254]
    website = (request.POST.get("website") or "").strip()[:200]
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

    ip_address, browser, operating_system = _client_details(request)
    comment = Comment(
        article=article,
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
    _sync_comment_images(comment, request.user if request.user.is_authenticated else None)

    if comment.is_approved and parent and parent.author_id:
        _notify(
            parent.author,
            request.user if request.user.is_authenticated else None,
            comment,
            CommentNotification.REPLY,
            "Someone replied to your comment",
            f"{comment.display_name} replied to your comment on {article.title}.",
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
        Comment,
        pk=comment_id,
        is_approved=True,
        article__is_published=True,
        article__created_at__lte=timezone.now(),
    )
    like, created = CommentLike.objects.get_or_create(comment=comment, user=request.user)
    if not created:
        like.delete()
    elif comment.author_id:
        _notify(
            comment.author,
            request.user,
            comment,
            CommentNotification.LIKE,
            "Someone liked your comment",
            f"{request.user.get_username()} liked your comment on {comment.article.title}.",
        )
    return JsonResponse({"ok": True, "liked": created, "like_count": comment.like_count})


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
    _sync_comment_images(comment, request.user)
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
        if not comment.is_sticky and Comment.objects.filter(
            article_id=comment.article_id, is_sticky=True
        ).exclude(pk=comment.pk).exists():
            return _json_error(_("Only one comment can be pinned at a time."), 409)
        comment.is_sticky = not comment.is_sticky
        comment.save(update_fields=("is_sticky", "updated_at"))
    return JsonResponse({"ok": True, "is_sticky": comment.is_sticky})


@require_GET
def notifications(request):
    if not request.user.is_authenticated:
        return _json_error(_("Please sign in to view notifications."), 401)
    items = CommentNotification.objects.filter(recipient=request.user).select_related("actor", "comment")[:50]
    return JsonResponse({
        "ok": True,
        "unread": CommentNotification.objects.filter(recipient=request.user, is_read=False).count(),
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
    })


@require_POST
def mark_notifications_read(request):
    if not request.user.is_authenticated:
        return _json_error(_("Please sign in to manage notifications."), 401)
    CommentNotification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return JsonResponse({"ok": True})


@require_GET
def comment_assets(request):
    site = _site()
    packs = []
    if site.comment_emoji_enabled:
        for pack in CommentEmojiPack.objects.filter(config=site, enabled=True).prefetch_related("items"):
            items = _emoji_pack_items(pack)
            packs.append({
                "name": pack.name,
                "icon": items[0]["url"] if items else "",
                "items": items,
            })
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
    source = CommentGifSource.objects.filter(config=site, enabled=True, pk=source_id).first()
    target = str(source.endpoint if source else "").strip()
    if _rate_limited(request, "gif", limit=30, period=60):
        return _json_error(_("Too many GIF searches. Please try again later."), 429)
    parsed = urlparse(target)
    if parsed.scheme != "https" or parsed.netloc.lower() != "api.giphy.com" or parsed.path.rstrip("/") not in {"/v1/gifs/search", "/v1/gifs/trending"}:
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
            headers={"Accept": "application/json", "User-Agent": "DjangoRedefineBlog/1.0"},
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
    if not _internal_comments_available(_site()):
        return _json_error(_("Internal comment uploads are disabled."), 403)
    if _rate_limited(request, "upload", limit=10, period=60 * 60):
        return _json_error(_("Too many image uploads. Please try again later."), 429)
    upload = request.FILES.get("image")
    max_bytes = settings.COMMENT_UPLOAD_MAX_BYTES
    if not upload or upload.size > max_bytes:
        return _json_error(_("Image must be smaller than %(size)s MB.") % {"size": max_bytes // (1024 * 1024)})
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
    extension = {"image/jpeg": "jpg", "image/png": "png", "image/gif": "gif", "image/webp": "webp"}[upload.content_type]
    path = f"comment-images/{uuid.uuid4().hex}.{extension}"
    # remove abandoned uploads opportunistically, so cancelled comments cannot
    # accumulate files forever even when no scheduled cleanup job is installed
    CommentImage.objects.filter(
        comment__isnull=True,
        created_at__lt=timezone.now() - timedelta(days=1),
    ).delete()
    try:
        saved = default_storage.save(path, upload)
        try:
            image = CommentImage.objects.create(uploader=request.user, image=saved)
        except Exception:
            default_storage.delete(saved)
            raise
    except Exception:
        logger.exception("Failed to save comment image upload")
        return _json_error(_("Image upload failed. Please try again later."), 500)
    return JsonResponse({"ok": True, "url": image.image.url})
