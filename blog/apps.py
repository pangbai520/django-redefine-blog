from django.apps import AppConfig


class BlogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "blog"

    def ready(self):
        from . import signals  # noqa: F401
        from .extensions import load_blog_extensions

        load_blog_extensions()
