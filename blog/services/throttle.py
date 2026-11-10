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
    """Share login limits across admin, HTML and AJAX authentication routes."""
    ip = get_client_ip(request) or "unknown"
    username = (request.POST.get("username") or "").strip().casefold()
    ip_digest = hashlib.sha256(ip.encode()).hexdigest()
    user_digest = hashlib.sha256(username.encode()).hexdigest()
    # Count both keys, even if one is exhausted. An authenticated session must
    # not change the IP key and rotating client IPs must not reset an account.
    ip_limited = _limited(f"auth:login:ip:{ip_digest}", 10, 15 * 60)
    user_limited = (
        _limited(f"auth:login:account:{user_digest}", 10, 15 * 60)
        if username else False
    )
    return ip_limited or user_limited
