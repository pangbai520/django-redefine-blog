from markdown.inlinepatterns import InlineProcessor

from ..blocks.redefine_tags import build_button


class ButtonInlineProcessor(InlineProcessor):
    def handleMatch(self, match, data):
        kind = match.group(1)
        element = build_button(kind, match.group(2) or "")
        return element, match.start(0), match.end(0)


BUTTON_RE = r"{%\s*(btn|button|cell)(?:\s+(.*?))?\s*%}"
