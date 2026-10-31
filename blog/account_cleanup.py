from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models import Subquery
from django.utils import timezone

from .models import PendingRegistration


CLEANUP_CACHE_KEY = "accounts:unverified-cleanup"


def cleanup_expired_unverified_accounts(*, hours=None):
    """Delete only accounts explicitly tracked as unfinished registrations."""
    retention_hours = (
        int(hours)
        if hours is not None
        else int(getattr(settings, "UNVERIFIED_ACCOUNT_RETENTION_HOURS", 72))
    )
    cutoff = timezone.now() - timedelta(hours=max(retention_hours, 1))
    pending_user_ids = PendingRegistration.objects.filter(
        created_at__lt=cutoff,
        user__is_active=False,
    ).values("user_id")
    deleted, details = get_user_model().objects.filter(
        pk__in=Subquery(pending_user_ids),
        is_active=False,
        is_staff=False,
        is_superuser=False,
    ).delete()
    user_label = get_user_model()._meta.label
    return int(details.get(user_label, 0)), deleted


def maybe_cleanup_expired_unverified_accounts():
    """Run at most once daily while registration traffic exists."""
    if not cache.add(CLEANUP_CACHE_KEY, True, 24 * 60 * 60):
        return 0
    count, _deleted = cleanup_expired_unverified_accounts()
    return count
