import json
import logging
import re
from urllib.parse import urljoin, urlparse

from django.core.cache import cache

from .remote import RemoteFetchError, fetch_https

logger = logging.getLogger(__name__)


def emoji_items(pack):
    """Load an emoji pack from configured rows or its remote manifest."""
    items = [{"name": item.name, "url": item.image_url} for item in pack.items.all()]
    if items or not pack.base_url:
        return items

    base = pack.base_url.rstrip("/")
    cache_key = f"comment-emoji-pack:{pack.pk}:{base}"
    cached = cache.get(cache_key)
    if cached is not None and _cache_valid(cached, base):
        return cached

    items = _discover_items(base)
    if items is None:
        logger.warning("Unable to discover emoji pack %s", pack.name)
        items = []

    cache.set(cache_key, items, 604800)
    return items


def _cache_valid(items, base):
    duplicate = "/" + base.rsplit("/", 1)[-1].lower() + "/"
    return all(
        str(item.get("url", "")).startswith(base + "/")
        and duplicate
        not in str(item.get("url", "")).lower().replace(base.lower(), "", 1)
        for item in items
    )


def _discover_items(base):
    try:
        items = _manifest_items(base)
        if items:
            return items

        raw = _directory_data(base)
        if not raw:
            return None
        return _listing_items(base, raw)
    except Exception:
        logger.debug("Emoji discovery failed for %s", base, exc_info=True)
        return None


def _manifest_items(base):
    try:
        response = fetch_https(base + "/info.json")
        if response.content_type not in {"application/json", "text/json", ""}:
            return []
        manifest = json.loads(response.body.decode("utf-8"))
    except (RemoteFetchError, UnicodeDecodeError, ValueError):
        return []

    prefix = str(manifest.get("prefix", ""))
    extension = str(manifest.get("type", "")).lstrip(".")
    entries = manifest.get("items", [])
    if not isinstance(entries, list):
        return []

    items = []
    for entry in entries[:500]:
        if isinstance(entry, dict):
            value = str(entry.get("name", entry.get("id", ""))).strip()
        else:
            value = str(entry).strip()
        if not value:
            continue

        filename = value
        if prefix and not filename.startswith(prefix):
            filename = prefix + filename
        if extension and not re.search(r"\.[a-z0-9]{2,5}$", filename, re.I):
            filename += "." + extension

        items.append(
            {
                "name": filename.rsplit("/", 1)[-1].rsplit(".", 1)[0],
                "url": base + "/" + filename,
            }
        )
    return items


def _directory_data(base):
    for url in (base + "/?meta", base + "/"):
        try:
            response = fetch_https(url)
            if response.content_type not in {
                "application/json",
                "text/html",
                "text/json",
                "text/plain",
                "",
            }:
                continue
            raw = response.body.decode("utf-8")
            if raw:
                return raw
        except (RemoteFetchError, UnicodeDecodeError):
            continue
    return ""


def _listing_items(base, raw):
    try:
        payload = json.loads(raw)
        entries = (
            payload
            if isinstance(payload, list)
            else payload.get(
                "files",
                payload.get("entries", []),
            )
        )
        links = [
            (
                entry.get("path", entry.get("url", ""))
                if isinstance(entry, dict)
                else str(entry)
            )
            for entry in entries
        ]
    except (TypeError, ValueError):
        links = re.findall(
            r'href=["\']([^"\']+\.(?:png|jpe?g|gif|webp))["\']',
            raw,
            re.I,
        )

    items = []
    for link in links[:500]:
        item = _link_item(base, link)
        if item is not None:
            items.append(item)
    return items


def _is_image(path):
    return bool(re.search(r"\.(?:png|jpe?g|gif|webp)$", str(path), re.I))


def _link_item(base, link):
    base_url = urlparse(base)
    raw_link = str(link).strip()
    if not re.match(r"^https?://", raw_link, re.I):
        path = raw_link.lstrip("/")
        base_name = base_url.path.rstrip("/").rsplit("/", 1)[-1]
        base_path = base_url.path.strip("/")
        if path.lower().startswith(base_name.lower() + "/"):
            path = path[len(base_name) + 1 :]
        if path.lower().startswith(base_path.lower() + "/"):
            raw_link = "/" + path
        else:
            raw_link = path
    image_url = urljoin(base.rstrip("/") + "/", raw_link)
    image = urlparse(image_url)
    base_port = base_url.port or 443
    image_port = image.port or 443
    base_path = base_url.path.rstrip("/") + "/"
    if (
        image.scheme.lower() != "https"
        or image.hostname != base_url.hostname
        or image_port != base_port
        or not image.path.startswith(base_path)
        or not _is_image(image.path)
    ):
        return None

    return {
        "name": image_url.rsplit("/", 1)[-1].rsplit(".", 1)[0],
        "url": image_url,
    }
