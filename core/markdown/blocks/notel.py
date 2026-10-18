import re
import xml.etree.ElementTree as etree

from markdown.blockprocessors import BlockProcessor

from .redefine_tags import _parse_markdown, _take_tag_content

class NotelProcessor(BlockProcessor):
    TAG_NAMES = r"noteL|notel|notelarge|notel-large|notes-large|subwarning"
    RE_START = re.compile(
        rf"^{{%\s*(?:{TAG_NAMES})(?:\s+(?P<args>.*?))?\s*%}}",
        re.IGNORECASE,
    )
    RE_END = re.compile(
        rf"{{%\s*end(?:{TAG_NAMES})\s*%}}",
        re.IGNORECASE,
    )

    def test(self, parent, block):
        return bool(self.RE_START.match(block))

    def run(self, parent, blocks):
        m_start = self.RE_START.match(blocks[0])
        args_str = m_start.group('args') or ''
        content = _take_tag_content(blocks, m_start, self.RE_END)
        if content is None:
            return False

        raw_args = args_str.split()
        if raw_args:
            color = raw_args[0]
            remaining_args = raw_args[1:]
            default_title = "Note"
        else:
            color = "default"
            remaining_args = []
            default_title = "Warning"
        fa_args = [a for a in remaining_args if a.startswith('fa-')]
        other_args = [a for a in remaining_args if not a.startswith('fa-')]
        if len(fa_args) >= 2:
            icon_class = f"notel-icon {fa_args[0]} {fa_args[1]}"
        elif len(fa_args) == 1:
            icon_class = f"notel-icon fa-solid {fa_args[0]}"
        else:
            icon_class = None
        title_text = " ".join(other_args) if other_args else default_title

        container = etree.SubElement(parent, "div", {"class": f"note-large {color}"})
        title_div = etree.SubElement(container, "div", {
            "class": "notel-title rounded-t-lg p-3 font-bold text-lg flex flex-row gap-2 items-center"
        })
        if icon_class:
            etree.SubElement(title_div, "i", {"class": icon_class})
        _parse_markdown(self.parser, title_div, title_text)

        content_div = etree.SubElement(container, "div", {"class": "notel-content markdown-body"})
        _parse_markdown(self.parser, content_div, content)

        return True
