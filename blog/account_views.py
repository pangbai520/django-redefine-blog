import logging
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import (
    authenticate,
    get_user_model,
    login,
    logout,
    update_session_auth_hash,
)
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    SetPasswordForm,
)
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.views import PasswordResetView
from django.core import signing
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_str
from django.utils.http import url_has_allowed_host_and_scheme, urlsafe_base64_decode
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .forms import (
    AccountDeletionForm,
    CommentRegistrationForm,
    UserEmailChangeForm,
    UserProfileForm,
)
from .models import CommentImage, PendingRegistration, SiteConfiguration, UserProfile
from .services.accounts import maybe_clean_unverified
from .services.mail import send_email_change, send_verify, send_welcome
from .services.throttle import rate_limited as _rate_limited

User = get_user_model()
logger = logging.getLogger(__name__)


def _site():
    return SiteConfiguration.get_config()


def _json_error(message, status=400):
    return JsonResponse({"ok": False, "error": message}, status=status)


class RateLimitedPasswordResetView(PasswordResetView):
    """Apply the same abuse controls to password mail as other account mail."""

    def form_valid(self, form):
        self.extra_email_context = {
            **(self.extra_email_context or {}),
            "language_code": getattr(
                self.request, "LANGUAGE_CODE", settings.LANGUAGE_CODE
            ),
            "site": _site(),
        }
        return super().form_valid(form)

    def post(self, request, *args, **kwargs):
        if _rate_limited(request, "password-reset", limit=5, period=60 * 60):
            form = self.get_form()
            form.add_error(
                None, _("Too many password reset requests. Please try again later.")
            )
            return self.render_to_response(self.get_context_data(form=form), status=429)
        return super().post(request, *args, **kwargs)


def _safe_next(request, candidate):
    if candidate and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return candidate
    return "/"


def _profile_redirect(return_to, **status):
    query = dict(status)
    if return_to != "/":
        query["next"] = return_to
    return redirect(f"{reverse('comment_profile')}?{urlencode(query)}")


def _delete_account(request):
    """Delete the login while preserving its published comments anonymously."""
    user = request.user
    with transaction.atomic():
        CommentImage.objects.filter(uploader=user, comment__isnull=True).delete()
        user.blog_comments.update(
            author=None,
            author_deleted=True,
            nickname="",
            email="",
            website="",
        )
        logout(request)
        user.delete()


def _create_user(request, form, site):
    """Create an account, removing it again when required mail cannot be delivered."""
    user = User.objects.create_user(
        username=form.cleaned_data["username"],
        email=form.cleaned_data["email"],
        password=form.cleaned_data["password"],
        is_active=not site.comment_require_email_verification,
    )
    if not site.comment_require_email_verification:
        return user
    PendingRegistration.objects.create(user=user)
    try:
        send_verify(request, user)
    except Exception:
        # do not leave an unusable account reserving the submitted name or email
        user.delete()
        raise
    return user


def _resend_verify(request, username, password):
    """Resend only when the submitted password proves account ownership."""
    user = User.objects.filter(username=username, is_active=False).first()
    if not user or not user.check_password(password):
        return None
    if _rate_limited(request, "verification-resend", limit=3, period=60 * 60):
        return False
    PendingRegistration.objects.get_or_create(user=user)
    try:
        send_verify(request, user)
    except Exception:
        logger.exception("Failed to resend verification email to user %s", user.pk)
        return False
    return True


def register(request):
    site = _site()
    maybe_clean_unverified()
    if not site.comment_registration_enabled:
        if request.headers.get("Accept") == "application/json":
            return _json_error(_("Registration is disabled."), 403)
        return render(
            request,
            "comments/register.html",
            {"form": None, "registration_disabled": True},
        )

    if request.method == "POST":
        form = CommentRegistrationForm(request.POST)
        if _rate_limited(request, "register", limit=5, period=60 * 60):
            form.add_error(
                None, _("Too many registration attempts. Please try again later.")
            )
            return render(request, "comments/register.html", {"form": form}, status=429)
        if form.is_valid():
            try:
                user = _create_user(request, form, site)
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
                return render(
                    request, "comments/register_done.html", {"email": user.email}
                )
            login(
                request,
                user,
                backend="django.contrib.auth.backends.ModelBackend",
            )
            return redirect(_safe_next(request, request.POST.get("next")))
    else:
        form = CommentRegistrationForm()
    return render(request, "comments/register.html", {"form": form})


@require_http_methods(["GET", "POST"])
def verify(request, uidb64, token):
    try:
        user = User.objects.get(pk=force_str(urlsafe_base64_decode(uidb64)))
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None
    token_valid = bool(
        user and not user.is_active and default_token_generator.check_token(user, token)
    )
    if request.method == "GET":
        return render(
            request,
            "comments/verify_done.html",
            {
                "already_verified": bool(user and user.is_active),
                "token_valid": token_valid,
                "email": user.email if user else "",
            },
            status=200 if token_valid or (user and user.is_active) else 400,
        )

    if token_valid:
        user.is_active = True
        user.save(update_fields=("is_active",))
        PendingRegistration.objects.filter(user=user).delete()
        login(
            request,
            user,
            backend="django.contrib.auth.backends.ModelBackend",
        )
        try:
            send_welcome(request, user)
        except Exception:
            logger.exception("Failed to send welcome email to user %s", user.pk)
        return render(request, "comments/verify_done.html", {"verified": True})
    return render(
        request,
        "comments/verify_done.html",
        {"already_verified": bool(user and user.is_active)},
        status=200 if user and user.is_active else 400,
    )


def login_view(request):
    login_limited = False
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if _rate_limited(request, "login", limit=10, period=15 * 60):
            login_limited = True
            form.add_error(
                None, _("Too many sign-in attempts. Please try again later.")
            )
        elif form.is_valid():
            login(request, form.get_user())
            if request.GET.get("modal") == "1":
                return render(request, "comments/login_modal_done.html")
            next_url = request.POST.get("next") or request.GET.get("next")
            return redirect(_safe_next(request, next_url))
    else:
        form = AuthenticationForm(request)
    if request.method == "POST" and not login_limited and not form.is_valid():
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        resend_result = _resend_verify(request, username, password)
        if resend_result is True:
            form.add_error(
                None,
                _(
                    "A new verification email was sent. Please check your inbox before signing in."
                ),
            )
        elif resend_result is False:
            form.add_error(
                None,
                _(
                    "We could not send a new verification email. Please try again later."
                ),
            )
    if request.GET.get("modal") == "1":
        template = "comments/login_modal.html"
    else:
        template = "comments/login.html"
    return render(request, template, {"form": form})


@require_POST
def login_ajax(request):
    if _rate_limited(request, "login", limit=10, period=15 * 60):
        return _json_error(_("Too many sign-in attempts. Please try again later."), 429)
    username = request.POST.get("username", "")
    password = request.POST.get("password", "")
    user = authenticate(request, username=username, password=password)
    if user is None:
        verification_sent = _resend_verify(request, username, password)
        return _json_error(
            (
                _(
                    "A new verification email was sent. Please check your inbox before signing in."
                )
                if verification_sent is True
                else (
                    _(
                        "We could not send a new verification email. Please try again later."
                    )
                    if verification_sent is False
                    else _("Invalid username or password.")
                )
            ),
            401,
        )
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return JsonResponse({"ok": True, "username": user.get_username()})


@require_POST
def register_ajax(request):
    site = _site()
    maybe_clean_unverified()
    if not site.comment_registration_enabled:
        return _json_error(_("Registration is disabled."), 403)
    if _rate_limited(request, "register", limit=5, period=60 * 60):
        return _json_error(
            _("Too many registration attempts. Please try again later."), 429
        )
    form = CommentRegistrationForm(request.POST)
    if not form.is_valid():
        errors = (
            str(error)
            for field_errors in form.errors.values()
            for error in field_errors
        )
        return _json_error(" ".join(errors))
    try:
        user = _create_user(request, form, site)
    except Exception:
        logger.exception(
            "Failed to complete account registration for %s",
            form.cleaned_data["email"],
        )
        return _json_error(
            _("Registration failed because the verification email could not be sent."),
            502,
        )
    if site.comment_require_email_verification:
        return JsonResponse({"ok": True, "pending": True})
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return JsonResponse({"ok": True, "pending": False})


@require_POST
def logout_view(request):
    next_url = _safe_next(request, request.POST.get("next"))
    logout(request)
    return redirect(next_url)


@login_required
def profile(request):
    profile_record, _profile_created = UserProfile.objects.get_or_create(
        user=request.user
    )
    public_display_name = profile_record.display_name
    public_website = profile_record.website
    public_avatar_name = profile_record.avatar.name
    response_status = 200
    return_to = _safe_next(
        request,
        request.POST.get("next") or request.GET.get("next"),
    )

    if request.method == "POST" and request.POST.get("action") == "cancel-email":
        profile_record.pending_email = ""
        profile_record.pending_email_requested_at = None
        profile_record.save(
            update_fields=("pending_email", "pending_email_requested_at")
        )
        return _profile_redirect(return_to, updated="1")

    if (
        request.method == "POST"
        and request.POST.get("action") == "cancel-profile-review"
    ):
        if profile_record.profile_review_pending:
            profile_record.clear_pending()
        return _profile_redirect(return_to, review="withdrawn")

    profile_form = UserProfileForm(
        instance=profile_record,
        initial={
            "display_name": (
                profile_record.pending_display_name
                if profile_record.profile_review_pending
                else profile_record.display_name
            ),
            "website": (
                profile_record.pending_website
                if profile_record.profile_review_pending
                else profile_record.website
            ),
        },
    )
    email_form = UserEmailChangeForm(user=request.user)
    password_is_set = request.user.has_usable_password()
    password_form_class = PasswordChangeForm if password_is_set else SetPasswordForm
    password_form = password_form_class(request.user)

    if request.method == "POST" and request.POST.get("action", "profile") == "profile":
        profile_form = UserProfileForm(
            request.POST,
            request.FILES,
            instance=profile_record,
        )
        if profile_form.is_valid():
            submitted_name = profile_form.cleaned_data["display_name"]
            submitted_website = profile_form.cleaned_data["website"]
            uploaded_avatar = (
                profile_form.cleaned_data.get("avatar")
                if "avatar" in request.FILES
                else None
            )
            remove_avatar = profile_form.cleaned_data.get("remove_avatar", False)
            site = _site()
            review_required = bool(
                site.comment_profile_review_enabled
                and not request.user.is_staff
                and not request.user.is_superuser
            )
            has_public_change = bool(
                submitted_name != public_display_name
                or submitted_website != public_website
                or uploaded_avatar is not None
                or (remove_avatar and public_avatar_name)
                or profile_record.profile_review_pending
            )
            if review_required and has_public_change:
                # ModelForm validation assigns cleaned values to its instance.
                # Restore the live identity before saving those values as a draft.
                profile_record.display_name = public_display_name
                profile_record.website = public_website
                profile_record.avatar = public_avatar_name
                profile_record.stage_profile_changes(
                    display_name=submitted_name,
                    website=submitted_website,
                    avatar=uploaded_avatar,
                    remove_avatar=remove_avatar,
                )
                return _profile_redirect(return_to, review="pending")

            updated_profile = profile_form.save(commit=False)
            if remove_avatar:
                updated_profile.avatar = None
            updated_profile.save()
            if updated_profile.profile_review_pending:
                updated_profile.clear_pending()
            return _profile_redirect(return_to, updated="1")

    if request.method == "POST" and request.POST.get("action") == "email":
        email_form = UserEmailChangeForm(request.POST, user=request.user)
        if not password_is_set:
            email_form.is_valid()
            email_form.add_error(
                None,
                _("Set a password before changing your email address."),
            )
            response_status = 400
        if password_is_set and email_form.is_valid():
            requested_email = email_form.cleaned_data["email"]
            if _rate_limited(request, "profile-email", limit=5, period=60 * 60):
                email_form.add_error(
                    "email",
                    _("Too many email-change requests. Please try again later."),
                )
                response_status = 429
            else:
                profile_record.pending_email = requested_email
                profile_record.pending_email_requested_at = timezone.now()
                profile_record.save(
                    update_fields=("pending_email", "pending_email_requested_at")
                )
                try:
                    send_email_change(request, request.user, requested_email)
                except Exception:
                    logger.exception(
                        "Failed to send email-change confirmation for user %s",
                        request.user.pk,
                    )
                    profile_record.pending_email = ""
                    profile_record.pending_email_requested_at = None
                    profile_record.save(
                        update_fields=("pending_email", "pending_email_requested_at")
                    )
                    email_form.add_error(
                        "email",
                        _(
                            "We could not send the confirmation email. "
                            "Your email address was not changed."
                        ),
                    )
                    response_status = 502
                else:
                    return _profile_redirect(return_to, email="pending")

    if request.method == "POST" and request.POST.get("action") == "password":
        password_form = password_form_class(request.user, request.POST)
        if password_form.is_valid():
            user = password_form.save()
            update_session_auth_hash(request, user)
            return _profile_redirect(return_to, password="updated")

    preview_display_name = (
        profile_record.pending_name
        if profile_record.profile_review_pending
        else profile_record.resolved_display_name
    )
    if profile_record.profile_review_pending and profile_record.pending_avatar_change:
        preview_avatar = profile_record.pending_avatar or None
    else:
        preview_avatar = profile_record.avatar or None

    return render(
        request,
        "comments/profile.html",
        {
            "profile_form": profile_form,
            "email_form": email_form,
            "password_form": password_form,
            "profile": profile_record,
            "profile_preview_display_name": preview_display_name,
            "profile_preview_avatar": preview_avatar,
            "return_to": return_to,
            "profile_updated": request.GET.get("updated") == "1",
            "profile_review_withdrawn": request.GET.get("review") == "withdrawn",
            "email_confirmation_sent": request.GET.get("email") == "pending",
            "password_updated": request.GET.get("password") == "updated",
            "password_is_set": password_is_set,
        },
        status=response_status,
    )


@login_required
@require_http_methods(["GET", "POST"])
def delete_account(request):
    return_to = _safe_next(
        request,
        request.POST.get("next") or request.GET.get("next"),
    )
    form = AccountDeletionForm(
        request.POST or None,
        user=request.user,
    )
    if request.method == "POST" and form.is_valid():
        _delete_account(request)
        return redirect(reverse("comment_account_deleted"))
    return render(
        request,
        "comments/delete_account_confirm.html",
        {"deletion_form": form, "return_to": return_to},
        status=400 if request.method == "POST" else 200,
    )


@require_GET
def account_deleted(request):
    return render(request, "comments/account_deleted.html")


@login_required
def profile_password_redirect(request):
    return_to = _safe_next(
        request,
        request.POST.get("next") or request.GET.get("next"),
    )
    target = f"{reverse('comment_profile')}?{urlencode({'next': return_to})}"
    return redirect(target + "#profile-password")


@require_GET
def profile_email_confirm(request, token):
    verified = False
    try:
        payload = signing.loads(
            token,
            salt="blog.profile-email-change",
            max_age=settings.PROFILE_EMAIL_CHANGE_MAX_AGE,
        )
        user = User.objects.get(pk=payload["user_id"], is_active=True)
        profile_record = UserProfile.objects.get(user=user)
        pending_email = str(payload["email"]).strip().lower()
        if (
            pending_email
            and profile_record.pending_email.casefold() == pending_email.casefold()
            and not User.objects.filter(email__iexact=pending_email)
            .exclude(pk=user.pk)
            .exists()
        ):
            with transaction.atomic():
                user.email = pending_email
                user.save(update_fields=("email",))
                profile_record.pending_email = ""
                profile_record.pending_email_requested_at = None
                profile_record.save(
                    update_fields=("pending_email", "pending_email_requested_at")
                )
            verified = True
    except (
        signing.BadSignature,
        signing.SignatureExpired,
        KeyError,
        TypeError,
        ValueError,
        User.DoesNotExist,
        UserProfile.DoesNotExist,
    ):
        pass
    return render(
        request,
        "comments/profile_email_confirm.html",
        {"verified": verified},
        status=200 if verified else 400,
    )
