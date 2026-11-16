from blog.middleware import get_client_ip

from .user_agent import parse_user_agent


def client_info(request):
    """Return the IP, browser and operating-system labels for a request."""
    browser, os_name = parse_user_agent(
        request.META.get("HTTP_USER_AGENT", ""),
        platform_version=request.META.get("HTTP_SEC_CH_UA_PLATFORM_VERSION", ""),
    )
    return get_client_ip(request), browser, os_name
