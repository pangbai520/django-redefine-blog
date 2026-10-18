import re
import xml.etree.ElementTree as etree

from markdown.postprocessors import Postprocessor
from markdown.treeprocessors import Treeprocessor


class ImageCaptionProcessor(Treeprocessor):
    def run(self, root):
        self._wrap_images(root)
        return root

    def _wrap_images(self, parent):
        for index, child in list(enumerate(list(parent))):
            if child.tag == "img" and child.get("alt", "").strip():
                figure = etree.Element("figure", {"class": "image-caption"})
                child.tail, original_tail = None, child.tail
                figure.append(child)
                caption = etree.SubElement(figure, "figcaption")
                caption.text = child.get("alt")
                figure.tail = original_tail
                parent.remove(child)
                parent.insert(index, figure)
            elif child.tag != "figure" or "image-caption" not in child.get("class", "").split():
                self._wrap_images(child)


class RawImageCaptionPostprocessor(Postprocessor):
    """Apply captions to authored HTML images after the HTML stash is restored."""

    IMAGE_RE = re.compile(r"<img\b(?P<attrs>[^<>]*?)(?P<slash>/?)>", re.IGNORECASE)
    FIGURE_RE = re.compile(
        r"<figure\b[^>]*class\s*=\s*(['\"])[^'\"]*\bimage-caption\b[^'\"]*\1[^>]*>"
        r"[\s\S]*?</figure>",
        re.IGNORECASE,
    )
    ALT_RE = re.compile(
        r"\balt\s*=\s*(?P<quote>['\"])(?P<value>.*?)(?P=quote)",
        re.IGNORECASE,
    )

    def run(self, text):
        output = []
        cursor = 0
        for figure_match in self.FIGURE_RE.finditer(text):
            output.append(self._caption_images(text[cursor:figure_match.start()]))
            output.append(figure_match.group(0))
            cursor = figure_match.end()
        output.append(self._caption_images(text[cursor:]))
        return "".join(output)

    def _caption_images(self, text):
        def add_caption(match):
            alt_match = self.ALT_RE.search(match.group("attrs"))
            if not alt_match or not alt_match.group("value").strip():
                return match.group(0)
            return (
                f'<figure class="image-caption">{match.group(0)}'
                f'<figcaption>{alt_match.group("value")}</figcaption></figure>'
            )

        return self.IMAGE_RE.sub(add_caption, text)
