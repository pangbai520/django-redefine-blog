import re

from markdown.postprocessors import Postprocessor


class DeleteMaskPostprocessor(Postprocessor):
    """Apply the reveal-on-hover class after raw HTML has been restored."""

    OPEN_TAG_RE = re.compile(r"<del(?P<attrs>\s[^>]*)?>", re.IGNORECASE)
    CLASS_RE = re.compile(r"(?P<prefix>\sclass\s*=\s*)(?P<quote>['\"])(?P<value>.*?)(?P=quote)", re.IGNORECASE)

    def run(self, text):
        def add_mask(match):
            attrs = match.group("attrs") or ""
            class_match = self.CLASS_RE.search(attrs)
            if class_match:
                classes = class_match.group("value").split()
                if "mask" in classes:
                    return match.group(0)
                classes.append("mask")
                replacement = (
                    f'{class_match.group("prefix")}{class_match.group("quote")}'
                    f'{" ".join(classes)}{class_match.group("quote")}'
                )
                attrs = attrs[:class_match.start()] + replacement + attrs[class_match.end():]
                return f"<del{attrs}>"
            return f'<del class="mask"{attrs}>'

        return self.OPEN_TAG_RE.sub(add_mask, text)
