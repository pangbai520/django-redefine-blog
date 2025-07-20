from django.core.cache import cache

from blog.middleware import get_client_ip


def rate_limited(request, action, limit=10, period=60):
    if request.user.is_authenticated:
        ident = request.user.pk
    else:
        ident = get_client_ip(request) or "unknown"

    key = f"comment:{action}:{ident}"
    if cache.add(key, 1, period):
        return False

    try:
        return cache.incr(key) > limit
    except ValueError:
        cache.set(key, 1, period)
        return False
