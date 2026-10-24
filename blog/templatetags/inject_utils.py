from django import template

register = template.Library()


class CaptureAsNode(template.Node):
    def __init__(self, nodelist, variable_name):
        self.nodelist = nodelist
        self.variable_name = variable_name

    def render(self, context):
        context[self.variable_name] = self.nodelist.render(context)
        return ""


@register.tag("captureas")
def capture_as(parser, token):
    bits = token.split_contents()
    if len(bits) != 2:
        raise template.TemplateSyntaxError(
            "captureas requires exactly one destination variable"
        )
    nodelist = parser.parse(("endcaptureas",))
    parser.delete_first_token()
    return CaptureAsNode(nodelist, bits[1])

@register.filter
def replace(value, arg):
    """
    Usage: {{ value|replace:"old,new" }}
    """
    if "," in arg:
        old, new = arg.split(",")
        return value.replace(old, new)
    return value
