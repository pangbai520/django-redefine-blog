import hashlib

from django.core.cache import cache
from django.utils import timezone
from django.views.decorators.cache import cache_page


CACHE_NAMESPACES = ("content", "search", "recommendations")


def cache_version(namespace):
    key = f"blog-cache-version:{namespace}"
    version = cache.get(key)
    if version is None:
        cache.add(key, 1, None)
        version = cache.get(key, 1)
    return version


def bump_cache_version(namespace):
    key = f"blog-cache-version:{namespace}"
    if not cache.add(key, 2, None):
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 2, None)


def invalidate_content_caches():
    for namespace in CACHE_NAMESPACES:
        bump_cache_version(namespace)
    cache.delete_many(("total_word_count", "site_stats_counts"))


def published_cache_timeout(default_timeout):
    from .models import ArticleModel

    next_publication = (
        ArticleModel.objects.filter(is_published=True, created_at__gt=timezone.now())
        .order_by("created_at")
        .values_list("created_at", flat=True)
        .first()
    )
    if next_publication is None:
        return default_timeout
    remaining = max(1, int((next_publication - timezone.now()).total_seconds()) + 1)
    return min(default_timeout, remaining)


def versioned_cache_page(namespace, timeout=3600):
    """Cache a public view until its content version or publish window changes."""
    def decorator(view):
        def wrapped(request, *args, **kwargs):
            version = cache_version(namespace)
            key_prefix = f"blog:{namespace}:v{version}"
            effective_timeout = published_cache_timeout(timeout)
            return cache_page(effective_timeout, key_prefix=key_prefix)(view)(
                request, *args, **kwargs
            )

        return wrapped

    return decorator


def query_cache_key(namespace, value):
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"blog:{namespace}:v{cache_version(namespace)}:{digest}"
