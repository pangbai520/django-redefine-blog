import re

from markdown.preprocessors import Preprocessor


class TabMarkerPreprocessor(Preprocessor):
    """Protect Redefine tab comments from Markdown's HTML comment stash."""

    START_RE = re.compile(r"<!--\s*tab\s+(.*?)\s*-->")
    END_RE = re.compile(r"<!--\s*endtab\s*-->")
    FENCE_RE = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})(?P<rest>.*)$")

    def run(self, lines):
        in_fence = False
        fence_character = ""
        fence_length = 0
        converted = []
        for line in lines:
            fence_match = self.FENCE_RE.match(line)
            if fence_match:
                marker = fence_match.group("fence")
                if not in_fence:
                    in_fence = True
                    fence_character = marker[0]
                    fence_length = len(marker)
                elif (
                    marker[0] == fence_character
                    and len(marker) >= fence_length
                    and not fence_match.group("rest").strip()
                ):
                    in_fence = False
                    fence_character = ""
                    fence_length = 0
                converted.append(line)
                continue

            if not in_fence:
                line = self.START_RE.sub(r"{% __redefine_tab \1 %}", line)
                line = self.END_RE.sub("{% __redefine_endtab %}", line)
            converted.append(line)
        return converted
