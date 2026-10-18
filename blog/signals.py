from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver
from django.core.cache import cache
from .models import ArticleModel, TrafficModel


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