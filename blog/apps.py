from django.apps import AppConfig
from django.conf import settings
from django.db.models.signals import post_migrate
from django.db.utils import OperationalError, ProgrammingError


def create_default_site_config(sender, **kwargs):
    try:
        from .starter_content import install_starter_content

        if getattr(settings, "INSTALL_STARTER_CONTENT", True):
            install_starter_content()
            from .signals import sync_owner_badges

            sync_owner_badges()
    except (OperationalError, ProgrammingError):
        # the table does not exist while the first migration is still running
        pass


class BlogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "blog"

    def ready(self):
        post_migrate.connect(
            create_default_site_config,
            sender=self,
            dispatch_uid="blog.install_starter_content",
        )
        from . import signals  # noqa: F401
        from .extensions import load_blog_extensions

        load_blog_extensions()
