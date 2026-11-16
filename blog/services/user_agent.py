"""Compact browser and operating-system labels used by comment cards."""

from __future__ import annotations

import re


UNKNOWN_BROWSER = "Unknown browser"
UNKNOWN_OS = "Unknown OS"


def _version(value):
    """Match Waline's display rule: keep at most two version components."""
    return ".".join(str(value or "").split(".")[:2]).strip(".")


def _browser_label(user_agent):
    patterns = (
        (r"MiuiBrowser/([\d.]+)", "MIUI Browser"),
        (r"(?:EdgiOS|EdgA|Edg)/([\d.]+)", "Edge"),
        (r"(?:QuarkPC|Quark)/([\d.]+)", "Quark"),
        (r"(?:HuaweiBrowser|HBPC)/([\d.]+)", "Huawei Browser"),
        (r"(?:MQQBrowser|QQBrowser)/([\d.]+)", "QQBrowser"),
        (r"UCBrowser/([\d.]+)", "UCBrowser"),
        (r"MicroMessenger/([\d.]+)", "WeChat"),
        (r"SamsungBrowser/([\d.]+)", "Samsung Internet"),
        (r"VivoBrowser/([\d.]+)", "Vivo Browser"),
        (r"baiduboxapp/([\d.]+)", "Baidu"),
        (r"OPR/([\d.]+)", "Opera"),
        (r"(?:FxiOS|Firefox)/([\d.]+)", "Firefox"),
        (r"(?:CriOS|Chrome)/([\d.]+)", "Chrome"),
    )
    for pattern, name in patterns:
        match = re.search(pattern, user_agent, re.IGNORECASE)
        if not match:
            continue
        if name == "Chrome" and "Mobile" in user_agent:
            name = "Mobile Chrome"
        version = _version(match.group(1))
        return f"{name}{version}" if version else name

    if "Safari/" in user_agent:
        match = re.search(r"Version/([\d.]+)", user_agent, re.IGNORECASE)
        version = _version(match.group(1)) if match else ""
        name = "Mobile Safari" if re.search(r"(?:iPhone|iPad|iPod|Mobile/)", user_agent) else "Safari"
        return f"{name}{version}" if version else name
    return UNKNOWN_BROWSER


def _operating_system_label(user_agent, platform_version=""):
    match = re.search(r"Windows NT ([\d.]+)", user_agent, re.IGNORECASE)
    if match:
        raw_version = match.group(1)
        versions = {
            "10.0": "Windows 10",
            "6.3": "Windows 8.1",
            "6.2": "Windows 8",
            "6.1": "Windows 7",
            "6.0": "Windows Vista",
            "5.1": "Windows XP",
        }
        label = versions.get(raw_version, f"Windows {raw_version}")
        hint = str(platform_version or "").strip('" ')
        if raw_version == "10.0" and hint:
            try:
                if int(hint.split(".", 1)[0]) >= 13:
                    label = "Windows 11"
            except ValueError:
                pass
        return label

    for pattern, name in (
        (r"Android[ /]([\d.]+)", "Android"),
        (r"(?:iPhone|CPU(?: iPhone)?|CPU) OS ([\d_]+)", "iOS"),
        (r"Mac OS X[ /]([\d_]+)", "macOS"),
    ):
        match = re.search(pattern, user_agent, re.IGNORECASE)
        if match:
            return f"{name} {match.group(1).replace('_', '.')}"

    if re.search(r"\bLinux\b", user_agent, re.IGNORECASE):
        architecture = re.search(
            r"\b(x86_64|amd64|i[3-6]86|aarch64|arm64|armv\d+l)\b",
            user_agent,
            re.IGNORECASE,
        )
        if architecture:
            value = architecture.group(1)
            aliases = {"amd64": "x86_64", "arm64": "aarch64"}
            return f"Linux {aliases.get(value.casefold(), value)}"
        return "Linux"
    return UNKNOWN_OS


def parse_user_agent(user_agent, *, platform_version=""):
    """Return Waline-style ``(browser, operating_system)`` labels."""
    value = str(user_agent or "")
    return (
        _browser_label(value)[:120],
        _operating_system_label(value, platform_version)[:120],
    )
