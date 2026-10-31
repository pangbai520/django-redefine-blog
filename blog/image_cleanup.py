import logging
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone


logger = logging.getLogger(__name__)
ORPHAN_IMAGE_CLEANUP_CACHE_KEY = "blog:comment-images:orphan-cleanup"
ORPHAN_IMAGE_MAX_AGE_HOURS = 24
ORPHAN_IMAGE_CLEANUP_INTERVAL = 24 * 60 * 60
ORPHAN_IMAGE_CLEANUP_BATCH_SIZE = 200


def maybe_cleanup_orphan_comment_images():
    """Bound automatic cleanup to one small batch per 24-hour period."""
    if not cache.add(
        ORPHAN_IMAGE_CLEANUP_CACHE_KEY,
        True,
        ORPHAN_IMAGE_CLEANUP_INTERVAL,
    ):
        return 0
    try:
        from .models import CommentImage

        cutoff = timezone.now() - timedelta(hours=ORPHAN_IMAGE_MAX_AGE_HOURS)
        orphan_ids = list(
            CommentImage.objects.filter(
                comment__isnull=True,
                created_at__lt=cutoff,
            )
            .order_by("created_at")
            .values_list("pk", flat=True)[:ORPHAN_IMAGE_CLEANUP_BATCH_SIZE]
        )
        for image in CommentImage.objects.filter(pk__in=orphan_ids).iterator():
            image.delete()
        if len(orphan_ids) == ORPHAN_IMAGE_CLEANUP_BATCH_SIZE:
            # Continue a large backlog soon without making the current request unbounded.
            cache.set(ORPHAN_IMAGE_CLEANUP_CACHE_KEY, True, 10 * 60)
        return len(orphan_ids)
    except Exception:
        cache.delete(ORPHAN_IMAGE_CLEANUP_CACHE_KEY)
        logger.exception("Failed to clean orphaned comment images")
        return 0
