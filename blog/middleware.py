import hashlib
import logging
from datetime import timedelta
from ipaddress import ip_address

from django.conf import settings
from django.core.cache import cache
from django.middleware.locale import LocaleMiddleware
from django.utils import timezone, translation
from django.utils.cache import patch_vary_headers
from .models import TrafficModel


logger = logging.getLogger(__name__)


class RegionLocaleMiddleware(LocaleMiddleware):
    """Choose a regional default while preserving the reader's own choice."""

    DEFAULT_LANGUAGE_MAP = {
        "CN": "zh-hans",
        "TW": "zh-tw",
        "HK": "zh-hk",
        # Macau uses the Hong Kong Traditional Chinese catalogue until a
        # dedicated Macau translation is added.
        "MO": "zh-hk",
    }

    def process_request(self, request):
        cookie_name = settings.LANGUAGE_COOKIE_NAME
        if (
            not getattr(settings, "REGION_LANGUAGE_DETECTION", True)
            or cookie_name in request.COOKIES
        ):
            return super().process_request(request)

        language_map = getattr(
            settings, "REGION_LANGUAGE_MAP", self.DEFAULT_LANGUAGE_MAP
        )
        for header in getattr(settings, "REGION_LANGUAGE_HEADERS", ()):
            country_code = request.headers.get(header, "").split(",", 1)[0].strip().upper()
            language = language_map.get(country_code)
            if language and translation.check_for_language(language):
                translation.activate(language)
                request.LANGUAGE_CODE = language
                request._region_language_header = header
                return None

        return super().process_request(request)

    def process_response(self, request, response):
        response = super().process_response(request, response)
        region_header = getattr(request, "_region_language_header", "")
        if region_header:
            patch_vary_headers(response, (region_header,))
        return response


def get_client_ip(request):
    candidate = request.META.get("REMOTE_ADDR", "")
    if getattr(settings, "TRUST_X_FORWARDED_FOR", False):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            candidate = forwarded.split(",", 1)[0].strip()
    try:
        return str(ip_address(candidate))
    except ValueError:
        return None


class TrafficModelMiddleware:
    EXCLUDED_PREFIXES = ("/static/", "/resources/", "/admin/", "/api/", "/favicon.ico")
    BOTS = (
        # exclude search crawlers, so indexing does not inflate reader traffic
        'googlebot', 'bingbot', 'baiduspider', 'yandexbot', 'sosospider',
        'sogou', '360spider', 'duckduckgo', 'ia_archiver', 'slurp',

        # exclude social previews, because link unfurling is not a human visit
        'facebookexternalhit', 'twitterbot', 'linkedinbot', 'whatsapp',
        'telegrambot', 'slackbot', 'discordbot', 'redditbot',

        # exclude scripted clients, so development and integration probes stay out of analytics
        'curl', 'wget', 'python', 'httpclient', 'urllib', 'requests',
        'aiohttp', 'java', 'go-http-client', 'node-fetch', 'axios', 'php',

        # exclude monitoring tools, because health checks would distort page views
        'lighthouse', 'gtmetrix', 'pingdom', 'sentry', 'updown',
        'statuscake', 'newrelic', 'headless', 'chrome-lighthouse',

        # keep generic markers last, so uncommon bots are still filtered conservatively
        'bot', 'spider', 'crawler', 'scrap', 'scan', 'audit', 'monitor',
        'semrushbot', 'ahrefsbot', 'dotbot', 'rogerbot', 'exabot'
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        content_type = response.get("Content-Type", "").lower()
        if (request.method == "GET" and response.status_code == 200
            and content_type.startswith("text/html")
            and not request.path.startswith(self.EXCLUDED_PREFIXES)):
            ua = request.META.get("HTTP_USER_AGENT", "").lower()
            client_ip = get_client_ip(request)
            if client_ip and ua and not any(bot in ua for bot in self.BOTS):
                self._record_traffic(request.path, client_ip, ua[:255])

        return response

    def _record_traffic(self, path, ip, ua):
        """Record at most one visit per address and path each hour."""
        digest = hashlib.sha256(f"{ip}\0{path}".encode("utf-8")).hexdigest()
        dedupe_key = f"blog:traffic:hour:{digest}"
        try:
            if not cache.add(dedupe_key, True, 60 * 60):
                return
            TrafficModel.objects.create(path=path, ip=ip, user_agent=ua)
            cleanup_key = "blog:traffic:retention-cleanup"
            if cache.add(cleanup_key, True, 60 * 60):
                retention_days = max(int(settings.TRAFFIC_RETENTION_DAYS), 1)
                cutoff = timezone.now() - timedelta(days=retention_days)
                expired_ids = list(
                    TrafficModel.objects.filter(created_at__lt=cutoff)
                    .order_by("created_at")
                    .values_list("pk", flat=True)[:1000]
                )
                if expired_ids:
                    TrafficModel.objects.filter(pk__in=expired_ids).delete()
                if len(expired_ids) < 1000:
                    cache.set(cleanup_key, True, 24 * 60 * 60)
        except Exception:
            # Analytics must never turn a successful page response into a 500.
            logger.exception("Failed to record traffic for %s", path)
