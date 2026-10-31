import ipaddress
import logging
import threading
from functools import lru_cache
from pathlib import Path

from django.conf import settings


logger = logging.getLogger(__name__)
_searchers = {}
_searcher_lock = threading.Lock()
_reported_failures = set()


def _database_path(version):
    setting_name = "IP2REGION_DB_V4" if version == 4 else "IP2REGION_DB_V6"
    value = str(getattr(settings, setting_name, "") or "").strip()
    return Path(value) if value else None


def _get_searcher(version):
    if version in _searchers:
        return _searchers[version]
    with _searcher_lock:
        if version in _searchers:
            return _searchers[version]
        path = _database_path(version)
        if path is None or not path.is_file():
            return None
        try:
            import ip2region.searcher as xdb
            import ip2region.util as util

            content = util.load_content_from_file(str(path))
            searcher = xdb.new_with_buffer(
                util.IPv4 if version == 4 else util.IPv6,
                content,
            )
        except Exception as exc:
            failure_key = (version, str(path), type(exc).__name__)
            if failure_key not in _reported_failures:
                _reported_failures.add(failure_key)
                logger.warning("IP location database could not be loaded: %s", exc)
            return None
        _searchers[version] = searcher
        return searcher


def _strip_chinese_suffix(value):
    value = value or ""
    for suffix in ("壮族自治区", "回族自治区", "维吾尔自治区", "自治区", "特别行政区", "省", "市"):
        if value.endswith(suffix):
            return value[: -len(suffix)]
    return value


def format_ip2region_result(region):
    fields = ["" if value == "0" else value.strip() for value in (region or "").split("|")]
    fields += [""] * (5 - len(fields))
    country, province, city, _isp, country_code = fields[:5]
    if not any((country, province, city)):
        return ""
    if country_code.upper() == "CN" or country == "中国":
        province = _strip_chinese_suffix(province)
        city = _strip_chinese_suffix(city)
        if province and city and province == city:
            city = ""
        return f"{province}{city}" or country
    parts = []
    for value in (country, province, city):
        if value and value not in parts:
            parts.append(value)
    return " · ".join(parts)


@lru_cache(maxsize=4096)
def get_ip_location(address):
    """Resolve an address locally; return an empty string when unavailable."""
    try:
        parsed = ipaddress.ip_address(str(address or "").strip())
    except ValueError:
        return ""
    if any((parsed.is_private, parsed.is_loopback, parsed.is_link_local, parsed.is_unspecified)):
        return ""
    searcher = _get_searcher(parsed.version)
    if searcher is None:
        return ""
    try:
        return format_ip2region_result(searcher.search(str(parsed)))
    except Exception:
        return ""
