import logging

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core import signing
from django.core.mail import EmailMultiAlternatives, send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from blog.models import CommentNotification, SiteConfiguration

logger = logging.getLogger(__name__)


def notify(recipient, actor, comment, kind, subject, body):
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
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [recipient.email])
    except Exception:
        logger.exception("Failed to send comment notification to %s", recipient.email)


def send_verify(request, user):
    """Send an activation link or raise when the mail backend rejects it."""
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
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
    }
    _send_template(
        request,
        email,
        "profile_email_change",
        context,
        "The email-change confirmation was not accepted by the mail backend.",
    )


def _send_template(request, recipient, template, context, error):
    subject = render_to_string(
        f"emails/{template}_subject.txt",
        context,
        request=request,
    ).strip()
    message = EmailMultiAlternatives(
        subject,
        render_to_string(
            f"emails/{template}.txt",
            context,
            request=request,
        ),
        settings.DEFAULT_FROM_EMAIL,
        [recipient],
    )
    message.attach_alternative(
        render_to_string(
            f"emails/{template}.html",
            context,
            request=request,
        ),
        "text/html",
    )
    if message.send() != 1:
        raise RuntimeError(error)
