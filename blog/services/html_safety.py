from copy import deepcopy

import nh3


_TAGS = nh3.ALLOWED_TAGS | {
    "button",
    "details",
    "div",
    "figcaption",
    "figure",
    "i",
    "input",
    "summary",
}

_ATTRS = deepcopy(nh3.ALLOWED_ATTRIBUTES)
_ATTRS["*"] = {"class", "id", "role", "title"}
_ATTRS["a"] = {"href", "name", "target", "title"}
_ATTRS["blockquote"] = {"cite"}
_ATTRS["button"] = {"disabled", "type"}
_ATTRS["details"] = {"open"}
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
_ATTRS["td"] = {"align", "colspan", "headers", "rowspan"}
_ATTRS["th"] = {"align", "colspan", "headers", "rowspan", "scope"}
_ATTRS["time"] = {"datetime"}

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
