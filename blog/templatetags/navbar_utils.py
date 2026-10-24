from django import template
from django.utils.translation import gettext_lazy

register = template.Library()

THEME_LABELS = {
    "home": gettext_lazy("Home"),
    "archives": gettext_lazy("Archives"),
    "categories": gettext_lazy("Categories"),
    "tags": gettext_lazy("Tags"),
    "friends": gettext_lazy("Friends"),
    "bookmarks": gettext_lazy("Bookmarks"),
    "essays": gettext_lazy("Essays"),
    "masonry": gettext_lazy("Masonry"),
    "more": gettext_lazy("More"),
    "admin": gettext_lazy("Admin"),
}


@register.filter
def theme_label(value):
    """Translate Redefine's standard labels without changing custom names."""
    return THEME_LABELS.get(str(value).casefold(), value)

@register.filter
def is_active(nav_link, request):
    if not request.resolver_match:
        return False

    match = request.resolver_match
    current_path = request.path
    link_url = nav_link.url

    if current_path == '/' and link_url == '/':
        return True

    if link_url != '/' and current_path.rstrip('/') == link_url.rstrip('/'):
        return True

    namespace = getattr(nav_link, 'inferred_namespace', None)
    if not namespace:
        return False

    if match.app_name == namespace:
        return True

    if match.view_name and match.view_name.startswith(namespace):
        return True

    return False
