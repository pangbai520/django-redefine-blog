import re
import xml.etree.ElementTree as etree

from markdown.blockprocessors import BlockProcessor


def _take_tag_content(blocks, start_match, end_re):
    """Return a complete tag body, leaving input untouched when it is unclosed."""
    chunks = [blocks[0][start_match.end():].lstrip("\r\n")]

    for block_index in range(len(blocks)):
        if block_index:
            chunks.append(blocks[block_index])
        current = chunks[-1]
        end_match = end_re.search(current)
        if not end_match:
            continue

        chunks[-1] = current[:end_match.start()]
        remainder = current[end_match.end():].lstrip("\r\n")
        del blocks[:block_index + 1]
        if remainder.strip():
            blocks.insert(0, remainder)
        return "\n\n".join(chunks).strip()

    # an incomplete tag should remain visible Markdown, rather than consuming
    # every block that follows it and making the rest of an article disappear
    return None


def _parse_markdown(parser, parent, content):
    if content:
        parser.parseBlocks(parent, content.split("\n\n"))


def _split_args(value):
    delimiter = "::" if "::" in value else ","
    return [part.strip() for part in value.split(delimiter)]


def build_button(kind, args):
    values = _split_args(args)
    if kind == "cell":
        text = values[0] if values else ""
        url = values[1] if len(values) > 1 else ""
        icon_or_image = values[2] if len(values) > 2 else ""
        anchor = etree.Element("a", {"class": "button", "title": text})
        if url:
            anchor.set("href", url)
        if icon_or_image:
            if "fa-" in icon_or_image:
                icon = etree.SubElement(anchor, "i", {"class": icon_or_image})
                icon.tail = f" {text}"
            else:
                image = etree.SubElement(anchor, "img", {"src": icon_or_image})
                image.tail = text
        else:
            anchor.text = text
        return anchor

    css_class = ""
    text = ""
    url = ""
    icon_class = ""
    if len(values) >= 4:
        css_class, text, url, icon_class = values[:4]
    elif len(values) == 3:
        if "fa-" in values[2]:
            text, url, icon_class = values
        else:
            css_class, text, url = values
    elif len(values) == 2:
        text, url = values
    elif values:
        text = values[0]

    classes = "button" + (f" {css_class}" if css_class else "")
    anchor = etree.Element("a", {"class": classes, "title": text})
    if url:
        anchor.set("href", url)
    if icon_class:
        icon = etree.SubElement(anchor, "i", {"class": icon_class})
        icon.tail = f" {text}"
    else:
        anchor.text = text
    return anchor


class NoteProcessor(BlockProcessor):
    START_RE = re.compile(r"^{%\s*(?P<tag>note|notes|subnote)(?:\s+(?P<args>.*?))?\s*%}")

    def test(self, parent, block):
        return bool(self.START_RE.match(block))

    def run(self, parent, blocks):
        match = self.START_RE.match(blocks[0])
        tag = match.group("tag")
        content = _take_tag_content(
            blocks,
            match,
            re.compile(r"{%\s*end(?:note|notes|subnote)\s*%}"),
        )
        if content is None:
            return False
        raw_args = (match.group("args") or "default").split()
        classes = [raw_args.pop(0) if raw_args else "default"]
        fa_args = [arg for arg in raw_args if arg.startswith("fa-")]
        classes.extend(arg for arg in raw_args if not arg.startswith("fa-"))

        icon_class = ""
        if len(fa_args) >= 2:
            icon_class = f"note-icon {fa_args[0]} {fa_args[1]}"
        elif fa_args:
            icon_class = f"note-icon fa-solid {fa_args[0]}"
        if icon_class:
            classes.append("icon-padding")

        container = etree.SubElement(parent, "div", {
            "class": f"note p-4 mb-4 rounded-small markdown-body {' '.join(classes)}"
        })
        if icon_class:
            etree.SubElement(container, "i", {"class": icon_class})
        _parse_markdown(self.parser, container, content)
        return True


class FoldingProcessor(BlockProcessor):
    START_RE = re.compile(r"^{%\s*folding(?:\s+(?P<args>.*?))?\s*%}")
    END_RE = re.compile(r"{%\s*endfolding\s*%}")

    def test(self, parent, block):
        return bool(self.START_RE.match(block))

    def run(self, parent, blocks):
        match = self.START_RE.match(blocks[0])
        content = _take_tag_content(blocks, match, self.END_RE)
        if content is None:
            return False
        args = _split_args(match.group("args") or "")
        style = args[0] if args else ""
        title = args[1] if len(args) > 1 else ""

        attrs = {"data-header-exclude": ""}
        if style:
            attrs["class"] = style
        details = etree.SubElement(parent, "details", attrs)
        summary = etree.SubElement(details, "summary")
        icon = etree.SubElement(summary, "i", {"class": "fa-solid fa-chevron-right"})
        icon.tail = f"{title} "
        body = etree.SubElement(details, "div", {"class": "content markdown-body"})
        _parse_markdown(self.parser, body, content)
        for element in body.iter():
            if element.tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
                heading = element.tag
                element.tag = "p"
                element.set("class", f"{heading} {element.get('class', '')}".strip())
        return True


class TabsProcessor(BlockProcessor):
    START_RE = re.compile(r"^{%\s*(?P<tag>tabs|subtabs|subsubtabs)(?:\s+(?P<args>.*?))?\s*%}")
    TAB_TOKEN_RE = re.compile(
        r"{%\s*(?:"
        r"(?P<tab>__redefine_tab)\s+(?P<header>.*?)|"
        r"(?P<endtab>__redefine_endtab)|"
        r"(?P<nested_start>tabs|subtabs|subsubtabs)(?:\s+.*?)?|"
        r"end(?P<nested_end>tabs|subtabs|subsubtabs)"
        r")\s*%}",
        re.DOTALL,
    )

    def test(self, parent, block):
        return bool(self.START_RE.match(block))

    def run(self, parent, blocks):
        match = self.START_RE.match(blocks[0])
        tag = match.group("tag")
        content = _take_tag_content(
            blocks,
            match,
            re.compile(rf"{{%\s*end{tag}\s*%}}"),
        )
        if content is None:
            return False
        args = _split_args(match.group("args") or "")
        tab_name = args[0] if args else ""
        try:
            active_index = int(args[1]) if len(args) > 1 else 0
        except ValueError:
            active_index = 0
        slug = tab_name.lower().replace(" ", "-")

        container = etree.SubElement(parent, "div", {
            "class": "tabs",
            "id": f"tab-{slug}",
        })
        nav = etree.SubElement(container, "ul", {"class": "nav-tabs"})
        tab_content = etree.SubElement(container, "div", {"class": "tab-content"})

        for index, (header, pane_content) in enumerate(
            self._extract_tab_blocks(content),
            start=1,
        ):
            parameters = header.split("@", 1)
            caption = parameters[0].strip()
            icon_text = parameters[1] if len(parameters) > 1 else ""
            tab_slug = f"{slug}-{index}"
            is_active = active_index == index or (active_index == 0 and index == 1)
            active_class = " active" if is_active else ""

            item = etree.SubElement(nav, "li", {"class": f"tab{active_class}"})
            anchor = etree.SubElement(item, "a", {"class": f"#{tab_slug}"})
            anchor.text = (
                f"{self.parser.md.htmlStash.store(icon_text)}{caption}"
                if icon_text
                else caption
            )
            pane = etree.SubElement(tab_content, "div", {
                "class": f"tab-pane{active_class}",
                "id": tab_slug,
            })
            _parse_markdown(self.parser, pane, pane_content.strip())
        return True

    def _extract_tab_blocks(self, content):
        blocks = []
        header = None
        content_start = 0
        nested_depth = 0

        for token in self.TAB_TOKEN_RE.finditer(content):
            if header is None:
                if token.group("tab"):
                    header = token.group("header")
                    content_start = token.end()
                continue

            if token.group("nested_start"):
                nested_depth += 1
            elif token.group("nested_end") and nested_depth:
                nested_depth -= 1
            elif token.group("endtab") and not nested_depth:
                blocks.append((header, content[content_start:token.start()]))
                header = None

        return blocks


class ButtonsProcessor(BlockProcessor):
    START_RE = re.compile(r"^{%\s*(?P<tag>btns|buttons)(?:\s+(?P<args>.*?))?\s*%}")
    CELL_RE = re.compile(r"{%\s*cell(?:\s+(.*?))?\s*%}")

    def test(self, parent, block):
        return bool(self.START_RE.match(block))

    def run(self, parent, blocks):
        match = self.START_RE.match(blocks[0])
        tag = match.group("tag")
        content = _take_tag_content(
            blocks,
            match,
            re.compile(rf"{{%\s*end{tag}\s*%}}"),
        )
        if content is None:
            return False
        extra_classes = (match.group("args") or "").strip()
        classes = "btns" + (f" {extra_classes}" if extra_classes else "")
        container = etree.SubElement(parent, "div", {"class": classes})
        cursor = 0
        for cell_match in self.CELL_RE.finditer(content):
            gap = content[cursor:cell_match.start()].strip()
            if gap:
                _parse_markdown(self.parser, container, gap)
            container.append(build_button("cell", cell_match.group(1) or ""))
            cursor = cell_match.end()
        remainder = content[cursor:].strip()
        if remainder:
            _parse_markdown(self.parser, container, remainder)
        return True
