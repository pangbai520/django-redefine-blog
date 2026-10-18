from django import template

register = template.Library()

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
