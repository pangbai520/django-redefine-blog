from django import template
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe

from blog.extensions import get_template_hooks


register = template.Library()


@register.simple_tag(takes_context=True)
def absolute_uri(context, value):
    """Build an absolute URL for metadata while keeping templates portable."""
    request = context.get("request")
    if not request or not value:
        return value or ""
    return request.build_absolute_uri(str(value))


@register.simple_tag(takes_context=True)
def render_blog_hook(context, hook_name):
    """Render registered templates in deterministic priority order."""
    values = context.flatten()
    request = context.get("request")
    output = [
        render_to_string(hook.template_name, values, request=request)
        for hook in get_template_hooks(hook_name)
    ]
    return mark_safe("".join(output))
