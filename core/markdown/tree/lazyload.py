import re

from django.conf import settings
from markdown.postprocessors import Postprocessor
from markdown.treeprocessors import Treeprocessor


class LazyLoadProcessor(Treeprocessor):
    def run(self, root):
        static_url = getattr(settings, "STATIC_URL", "/static/")
        placeholder = f"{static_url.rstrip('/')}/images/loading.svg"
        for image in root.iter("img"):
            source = image.get("src")
            if (
                not source
                or image.get("lazyload") is not None
                or image.get("data-src") is not None
            ):
                continue
            image.set("lazyload", "")
            image.set("src", placeholder)
            image.set("data-src", source)
        return root


class RawImageLazyLoadPostprocessor(Postprocessor):
    """Add Redefine lazyload attributes to images written as raw HTML."""

    IMAGE_RE = re.compile(r"<img\b(?P<attrs>[^<>]*?)(?P<slash>/?)>", re.IGNORECASE)
    SRC_RE = re.compile(
        r"(?<![\w-])src\s*=\s*(?P<quote>['\"])(?P<value>.*?)(?P=quote)",
        re.IGNORECASE,
    )
    LAZY_RE = re.compile(r"(?:^|\s)lazyload(?:\s|=|$)", re.IGNORECASE)
    DATA_SRC_RE = re.compile(r"(?:^|\s)data-src\s*=", re.IGNORECASE)

    def run(self, text):
        static_url = getattr(settings, "STATIC_URL", "/static/")
        placeholder = f"{static_url.rstrip('/')}/images/loading.svg"

        def add_lazyload(match):
            attrs = match.group("attrs")
            source_match = self.SRC_RE.search(attrs)
            if (
                not source_match
                or not source_match.group("value")
                or self.LAZY_RE.search(attrs)
                or self.DATA_SRC_RE.search(attrs)
            ):
                return match.group(0)

            replacement = (
                f'lazyload="" src="{placeholder}" '
                f'data-src={source_match.group("quote")}'
                f'{source_match.group("value")}{source_match.group("quote")}'
            )
            attrs = attrs[:source_match.start()] + replacement + attrs[source_match.end():]
            return f'<img{attrs}{match.group("slash")}>'

        return self.IMAGE_RE.sub(add_lazyload, text)
