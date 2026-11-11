from copy import deepcopy

import nh3


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


def clean_html(value):
    """Keep Redefine markup while dropping active or executable HTML."""
    return _CLEANER.clean(value or "")
