from django import template


register = template.Library()


@register.simple_tag
def redefine_page_range(page):
    """Return Hexo-style pagination with compact gaps on long archives."""
    return page.paginator.get_elided_page_range(
        number=page.number,
        on_each_side=2,
        on_ends=1,
    )
