import logging

from django.conf import settings
from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils import translation
from django.utils.translation import gettext as _

from blog.models import CommentNotification, SiteConfiguration
from blog.services.tokens import registration_token_generator

logger = logging.getLogger(__name__)


def _display_name(user):
    profile = getattr(user, "profile", None)
    value = profile.resolved_display_name if profile else user.get_username()
    return " ".join(value.split())


def _language(user):
    profile = getattr(user, "profile", None)
    code = getattr(profile, "language_code", settings.LANGUAGE_CODE)
    supported = {value for value, _name in settings.LANGUAGES}
    return code if code in supported else settings.LANGUAGE_CODE


def _comment_context(request, recipient, actor, comment, kind, site):
    language_code = _language(recipient)
    with translation.override(language_code):
        actor_name = (
            comment.display_name
            if kind == CommentNotification.REPLY
            else _display_name(actor)
        )
        target = comment.article or comment.page
        target_title = (
            target.title
            if comment.article_id
            else target.localized_title(language_code)
        )
        values = {"actor_name": actor_name, "target_title": target_title}
        if kind == CommentNotification.REPLY:
            email_subject = _("%(actor_name)s replied to your comment") % values
            heading = _("New reply to your comment")
            notification_text = _(
                "%(actor_name)s replied to your comment on “%(target_title)s”."
            ) % values
        else:
            email_subject = _("%(actor_name)s liked your comment") % values
            heading = _("Your comment received a like")
            notification_text = _(
                "%(actor_name)s liked your comment on “%(target_title)s”."
            ) % values
    preview = " ".join((comment.content or "").split())
    if len(preview) > 280:
        preview = preview[:279].rstrip() + "…"
    comment_url = request.build_absolute_uri(target.get_absolute_url())
    return {
        "actor_name": actor_name,
        "comment_preview": preview,
        "comment_url": f"{comment_url}#comment-{comment.pk}",
        "email_subject": email_subject,
        "heading": heading,
        "kind": kind,
        "language_code": language_code,
        "recipient": recipient,
        "notification_text": notification_text,
        "site": site,
        "target_title": target_title,
    }


def notify(request, recipient, actor, comment, kind):
    if not recipient or recipient == actor:
        return

    notification, created = CommentNotification.objects.get_or_create(
        recipient=recipient,
        actor=actor,
        comment=comment,
        kind=kind,
    )
    site = SiteConfiguration.get_config()
    if not created or not site.comment_email_notifications or not recipient.email:
        return

    try:
        _send_template(
            request,
            recipient.email,
            "comment_notification",
            _comment_context(request, recipient, actor, comment, kind, site),
            "The comment notification was not accepted by the mail backend.",
        )
    except Exception:
        logger.exception("Failed to send comment notification to %s", recipient.email)


def send_verify(request, user):
    """Send an activation link or raise when the mail backend rejects it."""
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = registration_token_generator.make_token(user)
    verify_url = request.build_absolute_uri(
        reverse("comment_verify", kwargs={"uidb64": uid, "token": token})
    )
    context = {
        "language_code": getattr(
            request,
            "LANGUAGE_CODE",
            settings.LANGUAGE_CODE,
        ),
        "site": SiteConfiguration.get_config(),
        "user": user,
        "verify_url": verify_url,
    }
    _send_template(
        request,
        user.email,
        "verify_account",
        context,
        "The verification email was not accepted by the mail backend.",
    )


def send_welcome(request, user):
    """Thank a verified reader without making activation depend on SMTP."""
    context = {
        "language_code": getattr(
            request,
            "LANGUAGE_CODE",
            settings.LANGUAGE_CODE,
        ),
        "site": SiteConfiguration.get_config(),
        "user": user,
        "site_url": request.build_absolute_uri(reverse("index")),
    }
    _send_template(
        request,
        user.email,
        "welcome",
        context,
        "The welcome email was not accepted by the mail backend.",
    )


def send_email_change(request, user, email):
    token = signing.dumps(
        {"user_id": user.pk, "email": email},
        salt="blog.profile-email-change",
        compress=True,
    )
    context = {
        "confirm_url": request.build_absolute_uri(
            reverse("comment_profile_email_confirm", kwargs={"token": token})
        ),
        "email": email,
        "user": user,
        "site": SiteConfiguration.get_config(),
        "language_code": getattr(
            request, "LANGUAGE_CODE", settings.LANGUAGE_CODE
        ),
    }
    _send_template(
        request,
        email,
        "profile_email_change",
        context,
        "The email-change confirmation was not accepted by the mail backend.",
    )


def _send_template(request, recipient, template, context, error):
    language_code = context.get("language_code", settings.LANGUAGE_CODE)
    with translation.override(language_code):
        subject = render_to_string(
            f"emails/{template}_subject.txt",
            context,
            request=request,
        ).strip()
        body = render_to_string(
            f"emails/{template}.txt", context, request=request
        )
        html_body = render_to_string(
            f"emails/{template}.html",
            context,
            request=request,
        )
    message = EmailMultiAlternatives(
        subject, body, settings.DEFAULT_FROM_EMAIL, [recipient]
    )
    message.attach_alternative(html_body, "text/html")
    if message.send() != 1:
        raise RuntimeError(error)
