"""Small, explicit extension points for project-owned integrations.

Extensions are ordinary Python modules listed in ``BLOG_EXTENSION_MODULES``.
There is deliberately no directory scanning or admin-controlled import path:
enabling executable code remains a deployment decision.
"""

from dataclasses import dataclass
from importlib import import_module

from django.conf import settings


@dataclass(frozen=True, order=True)
class TemplateHook:
    priority: int
    template_name: str


_template_hooks = {}
_markdown_extensions = []
_loaded_modules = set()

SUPPORTED_TEMPLATE_HOOKS = frozenset(
    {
        "head",
        "body_start",
        "main_start",
        "main_end",
        "article_start",
        "article_after_content",
        "article_before_comments",
        "body_end",
    }
)


def register_template_hook(hook_name, template_name, *, priority=100):
    """Render ``template_name`` at one of the documented theme hook names."""
    if hook_name not in SUPPORTED_TEMPLATE_HOOKS:
        supported = ", ".join(sorted(SUPPORTED_TEMPLATE_HOOKS))
        raise ValueError(f"Unknown template hook {hook_name!r}. Supported hooks: {supported}.")
    if not isinstance(template_name, str) or not template_name.strip():
        raise ValueError("template_name must be a non-empty template path.")
    hook = TemplateHook(int(priority), template_name)
    hooks = _template_hooks.setdefault(hook_name, [])
    if hook not in hooks:
        hooks.append(hook)
        hooks.sort()
    return hook


def get_template_hooks(hook_name):
    return tuple(_template_hooks.get(hook_name, ()))


def register_markdown_extension(extension):
    """Append a Markdown extension instance, class or import path."""
    if extension not in _markdown_extensions:
        _markdown_extensions.append(extension)
    return extension


def get_markdown_extensions(site=None):
    resolved = []
    for extension in _markdown_extensions:
        # Markdown extension classes are callable too, but they must be passed
        # to Python-Markdown as classes rather than mistaken for site-aware
        # factories and instantiated with SiteConfiguration as an argument.
        is_site_factory = callable(extension) and not isinstance(extension, type)
        resolved.append(extension(site) if is_site_factory else extension)
    return resolved


def load_blog_extensions():
    """Import only extension modules explicitly enabled in settings."""
    for module_name in getattr(settings, "BLOG_EXTENSION_MODULES", ()):
        if module_name in _loaded_modules:
            continue
        import_module(module_name)
        _loaded_modules.add(module_name)


def reset_extension_registry():
    """Clear process-local registrations; intended for tests only."""
    _template_hooks.clear()
    _markdown_extensions.clear()
    _loaded_modules.clear()
