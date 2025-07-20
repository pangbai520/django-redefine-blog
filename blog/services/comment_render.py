import re
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlparse

from django.utils.html import escape
from markdown import Markdown

from core.markdown.blocks.code_block import render_highlighted_code

from blog.models import CommentEmojiPack
from blog.services.emoji import emoji_items


class CommentSanitizer(HTMLParser):
    """Keep the small safe HTML subset used by Waline comments."""

    allowed_tags = {
        "p",
        "br",
        "hr",
        "strong",
        "b",
        "em",
        "i",
        "del",
        "s",
        "code",
        "pre",
        "blockquote",
        "ul",
        "ol",
        "li",
        "a",
        "img",
        "font",
        "span",
    }
    void_tags = {"br", "hr", "img"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.output = []
        self.blocked = 0

    @staticmethod
    def safe_url(value):
        value = (value or "").strip()
        parsed = urlparse(value)
        if value.startswith("/") and not value.startswith("//"):
            return value
        if parsed.scheme.lower() in {"http", "https"} and parsed.netloc:
            return value
        return ""

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in {"script", "style"}:
            self.blocked += 1
            return
        if self.blocked or tag not in self.allowed_tags:
            return

        attrs = dict(attrs)
        safe_attrs = self._safe_attrs(tag, attrs)
        if safe_attrs is None:
            return

        values = "".join(f' {key}="{escape(value)}"' for key, value in safe_attrs)
        self.output.append(f"<{tag}{values}>")

    def _safe_attrs(self, tag, attrs):
        if tag == "a":
            href = self.safe_url(attrs.get("href"))
            if not href:
                return []
            return [
                ("href", href),
                ("target", "_blank"),
                ("rel", "nofollow noopener noreferrer"),
            ]

        if tag == "img":
            src = self.safe_url(attrs.get("src"))
            if not src:
                return None
            return self._image_attrs(attrs, src)

        if tag == "font":
            color = (attrs.get("color") or "").strip()
            if re.fullmatch(
                r"(?:#[0-9a-f]{3,8}|[a-z]{1,32}|rgb\([0-9%,.\s]+\))",
                color,
                re.I,
            ):
                return [("color", color)]
            return []

        if tag == "code":
            classes = [
                item
                for item in (attrs.get("class") or "").split()
                if item == "hljs" or re.fullmatch(r"language-[\w+-]+", item)
            ]
            return [("class", " ".join(classes))] if classes else []

        if tag == "span":
            classes = [
                item
                for item in (attrs.get("class") or "").split()
                if re.fullmatch(r"hljs-[a-z_]+", item)
                or item in {"function_", "class_"}
            ]
            return [("class", " ".join(classes))] if classes else []

        return []

    @staticmethod
    def _image_attrs(attrs, src):
        safe_attrs = [("src", src)]
        alt = (attrs.get("alt") or "").strip()
        if alt:
            safe_attrs.append(("alt", alt[:120]))

        source_classes = (attrs.get("class") or "").split()
        if "wl-emoji" in source_classes or re.match(
            r"^(?:bmoji|tieba)_",
            alt.lower(),
        ):
            css_class = "wl-emoji"
        else:
            css_class = "internal-comment-image"
        safe_attrs.append(("class", css_class))
        return safe_attrs

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"script", "style"}:
            self.blocked = max(0, self.blocked - 1)
        elif (
            not self.blocked and tag in self.allowed_tags and tag not in self.void_tags
        ):
            self.output.append(f"</{tag}>")

    def handle_data(self, data):
        if not self.blocked:
            self.output.append(escape(data))


def sanitize_html(value):
    parser = CommentSanitizer()
    parser.feed(value or "")
    parser.close()
    return "".join(parser.output)


def render_md(content):
    """Render the Markdown subset allowed in comments."""
    source = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", content or "")
    html = Markdown(extensions=["extra", "nl2br"], output_format="html5").convert(
        source
    )
    html = re.sub(
        r'<pre><code(?: class="language-(?P<language>[\w+-]+)")?>(?P<code>[\s\S]*?)</code></pre>',
        render_code,
        html,
    )
    return sanitize_html(html)


def render_code(match):
    language = (match.group("language") or "text").lower()
    raw_code = unescape(match.group("code"))
    highlighted = render_highlighted_code(raw_code, language)
    return f'<pre><code class="hljs language-{language}">' f"{highlighted}</code></pre>"


def render_emoji(content_html, site):
    if not site.comment_emoji_enabled:
        return content_html

    packs = CommentEmojiPack.objects.filter(config=site, enabled=True)
    for pack in packs.prefetch_related("items"):
        for item in emoji_items(pack):
            token = escape(f":{item['name']}:")
            image = (
                '<img class="wl-emoji internal-comment-emoji" '
                f'src="{escape(item["url"])}" alt="{escape(item["name"])}">'
            )
            content_html = content_html.replace(token, image)
    return content_html
