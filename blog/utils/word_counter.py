import re
from django.utils.html import strip_tags


CHAR_BASED_RE = re.compile(
    r"""
    [\u4E00-\u9FFF]      # 中日韩统一汉字
    |[\u3400-\u4DBF]     # CJK 扩展 A
    |[\uF900-\uFAFF]     # CJK 兼容汉字
    |[\u3040-\u309F]     # 日文平假名
    |[\u30A0-\u30FF]     # 日文片假名
    |[\uAC00-\uD7AF]     # 韩文 Hangul
    |[\u0E00-\u0E7F]     # 泰语
    |[\u0E80-\u0EFF]     # 老挝语
    |[\u1780-\u17FF]     # 高棉语
    |[\u1000-\u109F]     # 缅甸语
    |[\u0F00-\u0FFF]     # 藏文
    |[\u0600-\u06FF]     # 阿拉伯语
    |[\u0590-\u05FF]     # 希伯来语
    """,
    re.VERBOSE,
)


TOKEN_RE = re.compile(
    r"""
    [a-zA-Z0-9_]+
    |[\u00C0-\u024F]+    # 拉丁扩展
    |[\u0400-\u04FF]+    # 西里尔文（俄语等）
    |[\u0370-\u03FF]+    # 希腊文
    """,
    re.VERBOSE,
)


def _get_text_stats(html: str):
    if not html:
        return 0, 0

    text = strip_tags(html)
    char_count = len(CHAR_BASED_RE.findall(text))
    remaining = CHAR_BASED_RE.sub(" ", text)
    token_count = len(TOKEN_RE.findall(remaining))

    return char_count, token_count

def word_counter(html: str) -> int:
    chars, tokens = _get_text_stats(html)
    return chars + tokens

def reading_time_counter(html: str, cn_speed=300, en_speed=160) -> int:
    chars, tokens = _get_text_stats(html)
    if chars == 0 and tokens == 0:
        return 0
    total_time = (chars / cn_speed) + (tokens / en_speed)
    return max(1, round(total_time))
