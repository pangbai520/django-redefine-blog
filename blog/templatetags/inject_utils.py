from django import template

register = template.Library()

@register.filter
def replace(value, arg):
    """
    Usage: {{ value|replace:"old,new" }}
    """
    if "," in arg:
        old, new = arg.split(",")
        return value.replace(old, new)
    return value
