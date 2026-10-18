from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver
from django.core.cache import cache
from django.contrib.auth import get_user_model

from .models import (
    ArticleModel,
    CommentBadge,
    CommentBadgeAssignment,
    SiteConfiguration,
    TrafficModel,
)


@receiver([post_save, post_delete], sender=ArticleModel)
def clear_article_caches(sender, instance, **kwargs):
    cache.delete_many(("total_word_count", "site_stats_counts"))


@receiver(m2m_changed, sender=ArticleModel.category.through)
@receiver(m2m_changed, sender=ArticleModel.tags.through)
def clear_article_taxonomy_cache(sender, instance, **kwargs):
    cache.delete("site_stats_counts")


@receiver([post_save, post_delete], sender=TrafficModel)
def clear_traffic_cache(sender, instance, **kwargs):
    cache.delete("site_traffic")


def grant_owner_badge(user, config=None):
    """Grant the active site's owner badge without coupling it to a username."""
    if not user.is_superuser:
        return
    config = config or SiteConfiguration.objects.filter(is_active=True).first()
    if not config:
        return
    badge = CommentBadge.objects.filter(
        config=config,
        name="博主",
        enabled=True,
    ).first()
    if badge:
        CommentBadgeAssignment.objects.get_or_create(user=user, badge=badge)


def sync_owner_badges():
    """Backfill the owner badge for superusers created before this feature."""
    for user in get_user_model().objects.filter(is_superuser=True).iterator():
        grant_owner_badge(user)


@receiver(post_save, sender=get_user_model())
def grant_owner_badge_to_superuser(sender, instance, **kwargs):
    grant_owner_badge(instance)


@receiver(post_save, sender=CommentBadge)
def grant_new_owner_badge(sender, instance, **kwargs):
    if instance.name != "博主" or not instance.enabled:
        return
    for user in get_user_model().objects.filter(is_superuser=True).iterator():
        grant_owner_badge(user, config=instance.config)
