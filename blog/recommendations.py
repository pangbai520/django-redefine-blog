from django.core.cache import cache
from django.db.models import Case, Count, IntegerField, Q, Value, When

from .cache_utils import query_cache_key
from .models import ArticleModel


def related_articles(article, limit):
    """Rank related posts in SQL and cache only their ordered identifiers."""
    limit = max(0, min(int(limit or 0), 100))
    if not limit:
        return []

    category_ids = list(article.category.values_list("pk", flat=True))
    tag_ids = list(article.tags.values_list("pk", flat=True))
    signature = f"{article.pk}:{article.updated_at.isoformat()}:{category_ids}:{tag_ids}:{limit}"
    key = query_cache_key("recommendations", signature)
    article_ids = cache.get(key)
    if article_ids is None:
        candidates = ArticleModel.objects.published().exclude(pk=article.pk)
        candidates = candidates.annotate(
            shared_categories=(
                Count(
                    "category",
                    filter=Q(category__in=category_ids),
                    distinct=True,
                )
                if category_ids
                else Value(0, output_field=IntegerField())
            ),
            shared_tags=(
                Count("tags", filter=Q(tags__in=tag_ids), distinct=True)
                if tag_ids
                else Value(0, output_field=IntegerField())
            ),
        ).order_by("-shared_categories", "-shared_tags", "-created_at", "-pk")
        article_ids = list(candidates.values_list("pk", flat=True)[:limit])
        cache.set(key, article_ids, 6 * 60 * 60)

    if not article_ids:
        return []
    ordering = Case(
        *(When(pk=pk, then=position) for position, pk in enumerate(article_ids)),
        output_field=IntegerField(),
    )
    return list(
        ArticleModel.objects.filter(pk__in=article_ids)
        .prefetch_related("category", "tags")
        .order_by(ordering)
    )
