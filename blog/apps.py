from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class BlogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "blog"
    verbose_name = _("Blog content")

    def ready(self):
        from . import signals  # noqa: F401
        from .extensions import load_blog_extensions

        load_blog_extensions()
