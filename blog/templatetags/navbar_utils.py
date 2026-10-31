from django import template
from django.utils.translation import gettext_lazy

register = template.Library()

THEME_LABELS = {
    "home": gettext_lazy("Home"),
    "archive": gettext_lazy("Archive"),
    "archives": gettext_lazy("Archives"),
    "about": gettext_lazy("About"),
    "links": gettext_lazy("Links"),
    "link": gettext_lazy("Link"),
    "categories": gettext_lazy("Categories"),
    "category": gettext_lazy("Category"),
    "tags": gettext_lazy("Tags"),
    "tag": gettext_lazy("Tag"),
    "posts": gettext_lazy("Posts"),
    "post": gettext_lazy("Post"),
    "friends": gettext_lazy("Friends"),
    "friend": gettext_lazy("Friend"),
    "timeline": gettext_lazy("Timeline"),
    "shuoshuo": gettext_lazy("Shuoshuo"),
    "bookmarks": gettext_lazy("Bookmarks"),
    "essays": gettext_lazy("Essays"),
    "masonry": gettext_lazy("Masonry"),
    "recent posts": gettext_lazy("Recent Posts"),
    "tag cloud": gettext_lazy("Tag Cloud"),
    "tagcloud": gettext_lazy("Tag Cloud"),
    "comment": gettext_lazy("Comment"),
    "comments": gettext_lazy("Comments"),
    "rss feed": gettext_lazy("RSS Feed"),
    "share": gettext_lazy("Share"),
    "theme": gettext_lazy("Theme"),
    "changelog": gettext_lazy("Changelog"),
    "status": gettext_lazy("Status"),
    "top": gettext_lazy("Sticky"),
    "sticky": gettext_lazy("Sticky"),
    "more": gettext_lazy("More"),
    "admin": gettext_lazy("Admin"),
}


@register.filter
def theme_label(value):
    """Translate Redefine's standard labels without changing custom names."""
    return THEME_LABELS.get(str(value).strip().casefold(), value)


@register.filter
def menu_label(menu_link):
    """Prefer an admin-defined label, then a standard theme translation."""
    resolver = getattr(menu_link, "resolve_localized_name", None)
    if resolver is None:
        return theme_label(menu_link)

    value, is_explicit_translation = resolver()
    if is_explicit_translation:
        return value
    return theme_label(value)

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
