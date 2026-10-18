import math
from django import template

register = template.Library()

@register.simple_tag
def get_author_label(post_count, is_auto, label_list_str):
    if post_count <= 0:
        return "Lv1"

    level = math.floor(math.log2(post_count))
    level = 1 if level < 2 else level - 1

    if not is_auto and label_list_str:
        if isinstance(label_list_str, str):
            label_list = [label.strip() for label in label_list_str.split(',')]
        else:
            label_list = [str(label).strip() for label in label_list_str]
        if len(label_list) > 0:
            if level > len(label_list):
                return label_list[-1]
            return label_list[level - 1]

    return f"Lv{level}"
