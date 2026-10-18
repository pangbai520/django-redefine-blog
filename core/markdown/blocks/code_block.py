import re
import xml.etree.ElementTree as etree
from html import escape
from markdown.blockprocessors import BlockProcessor
from markdown.util import AtomicString

try:
    from pygments import lex
    from pygments.lexers import TextLexer, get_lexer_by_name
    from pygments.token import Comment, Error, Keyword, Name, Number, String
except ImportError:  # Syntax highlighting remains optional for minimal installs.
    lex = get_lexer_by_name = None
    TextLexer = None
    Comment = Error = Keyword = Name = Number = String = None


FENCED_BLOCK_START_RE = re.compile(
    r"^(?P<indent> {0,3})(?P<fence>`{3,}|~{3,})[ \t]*(?P<info>[^\n]*)?(?:\n|$)"
)


LANG_LABEL_MAP = {
    "bash": "Bash", "sh": "Bash", "shell": "Bash",
    "python": "Python", "py": "Python",
    "js": "JavaScript", "javascript": "JavaScript",
    "ts": "TypeScript", "typescript": "TypeScript",
    "html": "HTML", "xhtml": "HTML", "xml": "XML", "css": "CSS",
    "json": "JSON", "yaml": "YAML", "yml": "YAML",
    "text": "Text", "plaintext": "Text", "md": "Markdown", "markdown": "Markdown",
    "ejs": "EJS", "django": "Django", "jinja": "Jinja", "jinja2": "Jinja",
    "c": "C", "cpp": "C++", "c++": "C++",
    "java": "Java", "go": "Go", "golang": "Go",
}


def _token_class(token_type):
    if token_type in Error:
        return "hljs-meta"
    if token_type in Comment:
        return "hljs-comment"
    if token_type in Keyword:
        return "hljs-keyword"
    if token_type in Name.Function:
        return "hljs-title function_"
    if token_type in Name.Class:
        return "hljs-title class_"
    if token_type in Name:
        return "hljs-variable"
    if token_type in String:
        return "hljs-string"
    if token_type in Number:
        return "hljs-number"
    return None


def _highlight_template_lines(raw_code):
    pattern = re.compile(r"(<%[\s\S]*?%>|{%[\s\S]*?%}|{{[\s\S]*?}})")
    highlighted = []
    for line in raw_code.split("\n"):
        parts = []
        for part in pattern.split(line):
            if part:
                parts.append(("hljs-meta" if pattern.fullmatch(part) else None, part))
        highlighted.append(parts)
    return highlighted


def _highlight_lines(raw_code, language):
    expected_line_count = max(1, len(raw_code.split("\n")))
    lines = [[] for _ in range(expected_line_count)]
    if not lines:
        return [[(None, "")]]
    if lex is None:
        return [[(None, line)] for line in raw_code.splitlines()]
    if language in {"ejs", "django", "jinja", "jinja2", "liquid"}:
        return _highlight_template_lines(raw_code)

    try:
        lexer = get_lexer_by_name(language)
    except Exception:
        lexer = TextLexer()

    line_index = 0
    for token_type, value in lex(raw_code, lexer):
        chunks = value.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        for chunk_index, chunk in enumerate(chunks):
            if chunk:
                lines[line_index].append((_token_class(token_type), chunk))
            if chunk_index < len(chunks) - 1:
                line_index += 1
                if line_index >= len(lines):
                    lines.append([])
    return lines[:expected_line_count]


def render_highlighted_code(raw_code, language="text"):
    """return escaped Highlight.js-compatible markup for one code block."""
    language = (language or "text").lower()
    if not re.fullmatch(r"[\w+-]+", language):
        language = "text"

    rendered_lines = []
    for line_parts in _highlight_lines(raw_code, language):
        rendered_parts = []
        for class_name, text in line_parts:
            escaped_text = escape(text)
            if class_name:
                rendered_parts.append(
                    f'<span class="{class_name}">{escaped_text}</span>'
                )
            else:
                rendered_parts.append(escaped_text)
        rendered_lines.append("".join(rendered_parts))
    return "\n".join(rendered_lines)

class CodeBlockProcessor(BlockProcessor):
    mermaid = False

    def test(self, parent, block):
        return bool(FENCED_BLOCK_START_RE.match(block))

    def run(self, parent, blocks):
        opening_block = blocks.pop(0)
        match = FENCED_BLOCK_START_RE.match(opening_block)
        fence = match.group("fence")
        fence_character = re.escape(fence[0])
        closing_re = re.compile(
            rf"^ {{0,3}}{fence_character}{{{len(fence)},}}[ \t]*$"
        )

        info = (match.group("info") or "").strip()
        if info.startswith("{") and info.endswith("}"):
            info = info[1:-1].strip()
        language_token = info.split(None, 1)[0] if info else "text"
        lang = language_token.lstrip(".").lower()
        if not re.fullmatch(r"[\w+-]+", lang):
            lang = "text"

        pending_blocks = [opening_block[match.end():]]
        closing_found = False
        code_lines = []
        while pending_blocks or blocks:
            if not pending_blocks:
                # markdown splits blocks at blank lines, so put the separator
                # back before inspecting the next part of the fenced block
                if code_lines != [""]:
                    code_lines.append("")
                pending_blocks.append(blocks.pop(0))

            current = pending_blocks.pop(0)
            lines = current.split("\n")
            for line_index, line in enumerate(lines):
                if closing_re.fullmatch(line):
                    remainder = "\n".join(lines[line_index + 1:]).lstrip("\r\n")
                    if remainder.strip():
                        blocks.insert(0, remainder)
                    closing_found = True
                    break
                code_lines.append(line)
            if closing_found:
                break

        raw_code = "\n".join(code_lines)
        if raw_code.endswith("\n"):
            raw_code = raw_code[:-1]

        if lang == "mermaid" and self.mermaid:
            diagram = etree.SubElement(parent, "pre", {"class": "mermaid"})
            diagram.text = AtomicString(raw_code)
            return True

        code_lines = raw_code.split('\n')

        label = LANG_LABEL_MAP.get(lang, lang.capitalize())

        container = etree.SubElement(parent, "div", {
            "class": "code-container",
            "data-rel": label,
        })

        highlight_container = etree.SubElement(container, "div", {"class": "highlight-container"})

        figure = etree.SubElement(highlight_container, "figure", {
            "class": f"iseeu highlight {lang}",
            "data-language": lang,
        })

        table = etree.SubElement(figure, "table")
        tbody = etree.SubElement(table, "tbody")
        tr = etree.SubElement(tbody, "tr")

        td_gutter = etree.SubElement(tr, "td", {"class": "gutter"})
        pre_gutter = etree.SubElement(td_gutter, "pre")

        for i in range(1, len(code_lines) + 1):
            s = etree.SubElement(pre_gutter, "span", {"class": "line"})
            s.text = str(i)
            etree.SubElement(pre_gutter, "br")

        td_code = etree.SubElement(tr, "td", {"class": "code"})
        pre_code = etree.SubElement(td_code, "pre")

        highlighted_lines = _highlight_lines(raw_code, lang)
        for line_parts in highlighted_lines:
            s = etree.SubElement(pre_code, "span", {"class": "line"})
            if not line_parts:
                s.text = " "
            else:
                for index, (class_name, text) in enumerate(line_parts):
                    if class_name:
                        target = etree.SubElement(s, "span", {"class": class_name})
                    elif index == 0:
                        target = s
                    else:
                        target = etree.SubElement(s, "span")
                    target.text = text
                if not s.text and not list(s):
                    s.text = " "
            etree.SubElement(pre_code, "br")

        figure.set("data-highlighted", "true")

        copy_btn = etree.SubElement(highlight_container, "div", {"class": "copy-button"})
        etree.SubElement(copy_btn, "i", {"class": "fa-regular fa-copy"})

        fold_btn = etree.SubElement(highlight_container, "div", {"class": "fold-button"})
        etree.SubElement(fold_btn, "i", {"class": "fa-solid fa-chevron-down"})

        return True
