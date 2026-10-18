import xml.etree.ElementTree as etree

from markdown.inlinepatterns import InlineProcessor


class StrikethroughInlineProcessor(InlineProcessor):
    """Render the GFM strikethrough syntax used by Hexo's Markdown renderer."""

    def __init__(self, pattern, md, masked=False):
        super().__init__(pattern, md)
        self.masked = masked

    def handleMatch(self, match, data):
        attributes = {"class": "mask"} if self.masked else {}
        element = etree.Element("del", attributes)
        element.text = match.group(1)
        return element, match.start(0), match.end(0)


STRIKETHROUGH_RE = r"(?<!\\)~~(?=\S)(.+?)(?<=\S)~~"
