from copy import deepcopy
from hashlib import sha256
from html import escape
from html.parser import HTMLParser
import json
import re
import secrets
from urllib.parse import urlsplit, urlunsplit

import nh3
from django.db.utils import OperationalError, ProgrammingError


_DIMENSION_RE = re.compile(r"[1-9]\d{0,4}")
_FRAME_PERMISSIONS = {
    "accelerometer",
    "autoplay",
    "encrypted-media",
    "fullscreen",
    "gyroscope",
    "picture-in-picture",
    "web-share",
}


_TAGS = nh3.ALLOWED_TAGS | {
    "audio",
    "button",
    "details",
    "div",
    "figcaption",
    "figure",
    "font",
    "i",
    "input",
    "picture",
    "source",
    "summary",
    "track",
    "video",
}

_ATTRS = deepcopy(nh3.ALLOWED_ATTRIBUTES)
_ATTRS["*"] = {"class", "dir", "id", "lang", "role", "title"}
_ATTRS["a"] = {"download", "href", "hreflang", "name", "target", "title"}
_ATTRS["audio"] = {"autoplay", "controls", "loop", "muted", "preload", "src"}
_ATTRS["blockquote"] = {"cite"}
_ATTRS["button"] = {"disabled", "type"}
_ATTRS["details"] = {"open"}
_ATTRS["font"] = {"color", "face", "size"}
_ATTRS["img"] = {
    "alt",
    "decoding",
    "height",
    "lazyload",
    "loading",
    "src",
    "title",
    "width",
}
_ATTRS["input"] = {"checked", "disabled", "type"}
_ATTRS["li"] = {"value"}
_ATTRS["ol"] = {"reversed", "start", "type"}
_ATTRS["source"] = {"media", "sizes", "src", "srcset", "type"}
_ATTRS["td"] = {"align", "colspan", "headers", "rowspan"}
_ATTRS["th"] = {"align", "colspan", "headers", "rowspan", "scope"}
_ATTRS["time"] = {"datetime"}
_ATTRS["track"] = {"default", "kind", "label", "src", "srclang"}
_ATTRS["video"] = {
    "autoplay",
    "controls",
    "height",
    "loop",
    "muted",
    "playsinline",
    "poster",
    "preload",
    "src",
    "width",
}

_CLEANER = nh3.Cleaner(
    tags=_TAGS,
    clean_content_tags={"embed", "iframe", "math", "object", "script", "style", "svg", "template"},
    attributes=_ATTRS,
    generic_attribute_prefixes={"aria-", "data-"},
    url_schemes={"http", "https", "mailto", "tel"},
    link_rel="noopener noreferrer",
)


def _provider_rules():
    try:
        from blog.models import EmbedProvider

        return tuple(
            EmbedProvider.objects.filter(enabled=True)
            .order_by("host", "path_prefix", "pk")
            .values_list("host", "path_prefix")
        )
    except (OperationalError, ProgrammingError):
        return ()


def embed_provider_signature():
    serialized = json.dumps(
        _provider_rules(), ensure_ascii=True, separators=(",", ":")
    )
    return sha256(serialized.encode("utf-8")).hexdigest()


def _path_allowed(path, prefix):
    path = path or "/"
    if prefix.endswith("/"):
        return path.startswith(prefix)
    return path == prefix or path.startswith(f"{prefix}/")


def _trusted_url(value):
    source = (value or "").strip()
    if source.startswith("//"):
        source = f"https:{source}"
    try:
        parsed = urlsplit(source)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or port not in (None, 443)
    ):
        return None

    host = parsed.hostname.lower().rstrip(".")
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return None
    if not any(
        host == allowed_host and _path_allowed(parsed.path, path_prefix)
        for allowed_host, path_prefix in _provider_rules()
    ):
        return None

    netloc = host if port is None else f"{host}:443"
    return urlunsplit(("https", netloc, parsed.path or "/", parsed.query, ""))


def _frame_allow(value):
    permissions = []
    for item in (value or "").split(";"):
        permission = item.strip().split(None, 1)[0].lower() if item.strip() else ""
        if permission in _FRAME_PERMISSIONS and permission not in permissions:
            permissions.append(permission)
    return "; ".join(permissions)


def _trusted_iframe(attributes):
    values = {}
    for name, value in attributes:
        name = (name or "").lower()
        if name in values:
            return None
        values[name] = value

    source = _trusted_url(values.get("src"))
    if source is None:
        return None

    safe_attributes = [
        ('class', "trusted-embed"),
        ("src", source),
        ("loading", "lazy"),
        ("referrerpolicy", "strict-origin-when-cross-origin"),
    ]
    title = (values.get("title") or "").strip()[:200]
    if title:
        safe_attributes.append(("title", title))
    for name in ("width", "height"):
        value = (values.get(name) or "").strip()
        if _DIMENSION_RE.fullmatch(value):
            safe_attributes.append((name, value))
    permissions = _frame_allow(values.get("allow"))
    if permissions:
        safe_attributes.append(("allow", permissions))

    rendered = " ".join(
        f'{name}="{escape(value, quote=True)}"' for name, value in safe_attributes
    )
    if "allowfullscreen" in values:
        rendered += " allowfullscreen"
    return f"<iframe {rendered}></iframe>"


class _IframeExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.output = []
        self.embeds = {}
        self.skip_iframe = 0
        self.token_prefix = f"trusted_embed_{secrets.token_hex(16)}"

    def _placeholder(self, attributes):
        iframe = _trusted_iframe(attributes)
        if iframe is None:
            return
        token = f"__{self.token_prefix}_{len(self.embeds)}__"
        self.embeds[token] = iframe
        self.output.append(token)

    def handle_starttag(self, tag, attrs):
        if self.skip_iframe:
            if tag.lower() == "iframe":
                self.skip_iframe += 1
            return
        if tag.lower() == "iframe":
            self._placeholder(attrs)
            self.skip_iframe = 1
            return
        self.output.append(self.get_starttag_text())

    def handle_startendtag(self, tag, attrs):
        if self.skip_iframe:
            return
        if tag.lower() == "iframe":
            self._placeholder(attrs)
            return
        self.output.append(self.get_starttag_text())

    def handle_endtag(self, tag):
        if self.skip_iframe:
            if tag.lower() == "iframe":
                self.skip_iframe -= 1
            return
        self.output.append(f"</{tag}>")

    def handle_data(self, data):
        if not self.skip_iframe:
            self.output.append(data)

    def handle_entityref(self, name):
        if not self.skip_iframe:
            self.output.append(f"&{name};")

    def handle_charref(self, name):
        if not self.skip_iframe:
            self.output.append(f"&#{name};")

    def handle_comment(self, data):
        if not self.skip_iframe:
            self.output.append(f"<!--{data}-->")

    def handle_decl(self, decl):
        if not self.skip_iframe:
            self.output.append(f"<!{decl}>")

    def handle_pi(self, data):
        if not self.skip_iframe:
            self.output.append(f"<?{data}>")


def clean_html(value):
    """Keep Redefine markup while dropping active or executable HTML."""
    extractor = _IframeExtractor()
    extractor.feed(value or "")
    extractor.close()
    cleaned = _CLEANER.clean("".join(extractor.output))
    for token, iframe in extractor.embeds.items():
        cleaned = cleaned.replace(token, iframe)
    return cleaned
