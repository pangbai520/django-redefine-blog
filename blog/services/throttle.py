import hashlib

from django.core.cache import cache

from blog.middleware import get_client_ip


def rate_limited(request, action, limit=10, period=60):
    if request.user.is_authenticated:
        ident = request.user.pk
    else:
        ident = get_client_ip(request) or "unknown"

    key = f"comment:{action}:{ident}"
    return _limited(key, limit, period)


def _limited(key, limit, period):
    if cache.add(key, 1, period):
        return False

    try:
        return cache.incr(key) > limit
    except ValueError:
        cache.set(key, 1, period)
        return False


def login_rate_limited(request):
    """Share one IP limit across admin, HTML and AJAX authentication routes."""
    ip = get_client_ip(request) or "unknown"
    ip_digest = hashlib.sha256(ip.encode()).hexdigest()
    # Do not hard-lock a named account before checking its password. Otherwise
    # anyone who knows a username can deny that user access from every address.
    return _limited(f"auth:login:ip:{ip_digest}", 10, 15 * 60)
