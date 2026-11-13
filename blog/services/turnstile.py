import json
import logging
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils.translation import gettext as _


logger = logging.getLogger(__name__)
VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


class TurnstileUnavailable(Exception):
    pass


def _client_ip(request):
    value = request.META.get("REMOTE_ADDR", "")
    if settings.TRUST_X_FORWARDED_FOR:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            value = forwarded.split(",", 1)[0].strip()
    return value


def verify_turnstile(request, action):
    """Validate one single-use Turnstile token for a named public action."""
    if not settings.TURNSTILE_ENABLED:
        return True

    token = str(request.POST.get("cf-turnstile-response") or "").strip()
    if not token or len(token) > 2048:
        return False

    payload = {
        "secret": settings.TURNSTILE_SECRET_KEY,
        "response": token,
        "remoteip": _client_ip(request),
    }
    verification = Request(
        VERIFY_URL,
        data=urlencode(payload).encode("ascii"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "DjangoRedefine/1.0",
        },
        method="POST",
    )
    try:
        with urlopen(verification, timeout=settings.TURNSTILE_TIMEOUT) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
        logger.warning("Turnstile verification unavailable", exc_info=True)
        raise TurnstileUnavailable from exc

    if not result.get("success"):
        return False
    returned_action = str(result.get("action") or "")
    return returned_action == action


def turnstile_error(request, action):
    try:
        valid = verify_turnstile(request, action)
    except TurnstileUnavailable:
        return (
            _("Human verification is temporarily unavailable. Please try again later."),
            503,
        )
    if not valid:
        return (_("Please complete the human verification and try again."), 400)
    return None
