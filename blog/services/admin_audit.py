import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.signals import user_logged_in
from django.core.cache import cache
from django.db import DatabaseError
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone

from blog.middleware import get_client_ip
from blog.models import AdminLoginRecord


logger = logging.getLogger(__name__)


def _is_admin(request):
    return request is not None and request.path.startswith(reverse("admin:index"))


def _clean_records(now):
    if not cache.add("admin-login-audit:cleanup", True, 24 * 60 * 60):
        return
    days = max(int(settings.ADMIN_LOGIN_RETENTION_DAYS), 1)
    cutoff = now - timedelta(days=days)
    AdminLoginRecord.objects.filter(created_at__lt=cutoff).delete()


@receiver(user_logged_in, dispatch_uid="blog.record_admin_login")
def record_admin_login(sender, request, user, **kwargs):
    if not _is_admin(request) or not user.is_staff:
        return
    try:
        now = timezone.now()
        AdminLoginRecord.objects.create(
            user=user,
            username=user.get_username()[:150],
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
        )
        _clean_records(now)
    except DatabaseError:
        # Auditing must never lock an administrator out during a database
        # maintenance edge case. The failure remains visible in server logs.
        logger.exception("Unable to record an admin login")
