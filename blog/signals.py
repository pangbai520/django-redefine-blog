from django.db.models.signals import m2m_changed, post_delete, post_save, pre_save
from django.dispatch import receiver
from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.db.utils import OperationalError, ProgrammingError
from django.utils import timezone

from .models import (
    ArticleModel,
    Category,
    CommentImage,
    CommentBadge,
    CommentBadgeTranslation,
    CommentBadgeAssignment,
    Font,
    MenuLink,
    MenuLinkTranslation,
    SiteConfiguration,
    StandalonePage,
    StandalonePageTranslation,
    Tag,
    TrafficModel,
    UserProfile,
)


OWNER_BADGE_TRANSLATIONS = {
    "en": "Blogger",
    "es": "Bloguero",
    "fr": "Blogueur",
    "ja": "ブロガー",
    "zh-hans": "博主",
    "zh-hk": "部落客",
    "zh-tw": "部落客",
}


@receiver(post_delete, sender=CommentImage)
def delete_comment_image_file(sender, instance, **kwargs):
    """Remove storage objects after explicit, queryset, or cascade deletion."""
    if not instance.image or not instance.image.name:
        return
    storage = instance.image.storage
    name = instance.image.name
    from django.db import transaction

    def delete_if_unreferenced():
        if not CommentImage.objects.filter(image=name).exists():
            storage.delete(name)

    transaction.on_commit(delete_if_unreferenced)


@receiver(pre_save, sender=ArticleModel)
def remember_article_publication_state(sender, instance, **kwargs):
    if not instance.pk:
        instance._was_published = False
        return
    instance._was_published = sender.objects.filter(pk=instance.pk).values_list(
        "is_published", flat=True
    ).first()


@receiver(post_save, sender=ArticleModel)
def refresh_article_derivatives(sender, instance, **kwargs):
    from .extension_signals import article_published, article_unpublished
    from .cache_utils import invalidate_content_caches
    from .search import index_article

    index_article(instance)
    invalidate_content_caches()
    was_published = bool(getattr(instance, "_was_published", False))
    if instance.is_published and not was_published:
        article_published.send(
            sender=sender,
            instance=instance,
            created=kwargs.get("created", False),
        )
    elif was_published and not instance.is_published:
        article_unpublished.send(sender=sender, instance=instance)


@receiver(post_delete, sender=ArticleModel)
def remove_article_derivatives(sender, instance, **kwargs):
    from .extension_signals import article_deleted
    from .cache_utils import invalidate_content_caches
    from .search import remove_article_from_index

    remove_article_from_index(instance.pk)
    invalidate_content_caches()
    article_deleted.send(sender=sender, instance=instance)


@receiver(m2m_changed, sender=ArticleModel.category.through)
@receiver(m2m_changed, sender=ArticleModel.tags.through)
def refresh_article_taxonomy(sender, instance, action, **kwargs):
    if action not in {"post_add", "post_remove", "post_clear"}:
        return
    from .cache_utils import invalidate_content_caches
    from .search import index_article

    index_article(instance)
    invalidate_content_caches()


@receiver([post_save, post_delete], sender=Category)
@receiver([post_save, post_delete], sender=Tag)
def invalidate_taxonomy_content(sender, instance, **kwargs):
    from .cache_utils import invalidate_content_caches

    invalidate_content_caches()


@receiver([post_save, post_delete], sender=SiteConfiguration)
def invalidate_site_content(sender, instance, **kwargs):
    from .cache_utils import invalidate_content_caches

    invalidate_content_caches()


@receiver(post_save, sender=SiteConfiguration)
def create_default_standalone_pages(sender, instance, created, **kwargs):
    if not created or kwargs.get("raw"):
        return
    try:
        StandalonePage.objects.bulk_create(
            [
                StandalonePage(config=instance, page_type=page_type, **defaults)
                for page_type, defaults in StandalonePage.BUILTIN_DEFAULTS.items()
            ],
            ignore_conflicts=True,
        )
    except (OperationalError, ProgrammingError):
        # SiteConfiguration is created while migrations and test databases are
        # still bringing the page table online.
        pass


@receiver([post_save, post_delete], sender=StandalonePage)
@receiver([post_save, post_delete], sender=StandalonePageTranslation)
def invalidate_standalone_page_content(sender, instance, **kwargs):
    from .cache_utils import invalidate_content_caches

    config_id = instance.config_id if isinstance(instance, StandalonePage) else instance.page.config_id
    cache.delete(f"standalone-page-types:{config_id}")
    invalidate_content_caches()


@receiver([post_save, post_delete], sender=MenuLink)
@receiver([post_save, post_delete], sender=Font)
def touch_related_site_configuration(sender, instance, **kwargs):
    SiteConfiguration.objects.filter(pk=instance.config_id).update(
        updated_at=timezone.now()
    )
    cache.delete("actived_site_config")
    from .cache_utils import invalidate_content_caches

    invalidate_content_caches()


@receiver([post_save, post_delete], sender=MenuLinkTranslation)
def touch_translated_menu_configuration(sender, instance, **kwargs):
    config_id = MenuLink.objects.filter(pk=instance.menu_link_id).values_list(
        "config_id", flat=True
    ).first()
    if config_id:
        SiteConfiguration.objects.filter(pk=config_id).update(
            updated_at=timezone.now()
        )
        cache.delete("actived_site_config")
        from .cache_utils import invalidate_content_caches

        invalidate_content_caches()


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
        is_owner_badge=True,
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
    if instance.is_active:
        try:
            UserProfile.objects.get_or_create(user=instance)
        except (OperationalError, ProgrammingError):
            # auth users can be saved while the profile migration is still running
            pass
    grant_owner_badge(instance)
    if instance.is_superuser:
        from .cache_utils import invalidate_content_caches

        invalidate_content_caches()


@receiver([post_save, post_delete], sender=UserProfile)
def invalidate_owner_profile_content(sender, instance, **kwargs):
    if instance.user.is_superuser:
        from .cache_utils import invalidate_content_caches

        invalidate_content_caches()


@receiver(post_save, sender=CommentBadge)
def grant_new_owner_badge(sender, instance, **kwargs):
    if not instance.is_owner_badge or not instance.enabled:
        return
    CommentBadgeTranslation.objects.bulk_create(
        [
            CommentBadgeTranslation(
                badge=instance, language_code=language_code, name=name
            )
            for language_code, name in OWNER_BADGE_TRANSLATIONS.items()
        ],
        ignore_conflicts=True,
    )
    for user in get_user_model().objects.filter(is_superuser=True).iterator():
        grant_owner_badge(user, config=instance.config)


@receiver([post_save, post_delete], sender=CommentBadgeTranslation)
def invalidate_badge_translation_content(sender, instance, **kwargs):
    from .cache_utils import invalidate_content_caches

    invalidate_content_caches()
