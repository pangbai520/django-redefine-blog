import re

from blog.middleware import get_client_ip


def client_info(request):
    """Return the IP, browser and operating-system labels for a request."""
    user_agent = request.META.get("HTTP_USER_AGENT", "")
    browser = "Unknown browser"
    patterns = (
        (r"Edg/([\d.]+)", "Edge"),
        (r"OPR/([\d.]+)", "Opera"),
        (r"Chrome/([\d.]+)", "Chrome"),
        (r"Firefox/([\d.]+)", "Firefox"),
        (r"Version/([\d.]+).*Safari/", "Safari"),
    )
    for pattern, label in patterns:
        match = re.search(pattern, user_agent)
        if match:
            browser = f"{label}{match.group(1)}"
            break

    os_name = "Unknown OS"
    windows = re.search(r"Windows NT ([\d.]+)", user_agent)
    android = re.search(r"Android ([\d.]+)", user_agent)
    iphone = re.search(r"iPhone OS ([\d_]+)", user_agent)
    macos = re.search(r"Mac OS X ([\d_]+)", user_agent)

    if windows:
        versions = {
            "10.0": "Windows 10",
            "6.3": "Windows 8.1",
            "6.2": "Windows 8",
            "6.1": "Windows 7",
        }
        os_name = versions.get(windows.group(1), f"Windows {windows.group(1)}")
        hint = request.META.get("HTTP_SEC_CH_UA_PLATFORM_VERSION", "").strip('" ')
        if hint:
            try:
                if int(hint.split(".", 1)[0]) >= 13:
                    os_name = "Windows 11"
            except ValueError:
                pass
    elif android:
        os_name = f"Android {android.group(1)}"
    elif iphone:
        os_name = f"iOS {iphone.group(1).replace('_', '.')}"
    elif macos:
        os_name = f"macOS {macos.group(1).replace('_', '.')}"
    elif "Linux" in user_agent:
        os_name = "Linux"

    return get_client_ip(request), browser, os_name
