from django.apps import AppConfig
from django.db.models.signals import post_migrate
from django.db.utils import OperationalError, ProgrammingError


def create_default_site_config(sender, **kwargs):
    try:
        from .models import SiteConfiguration

        if not SiteConfiguration.objects.exists():
            SiteConfiguration.objects.create(
                config_name="Default Config",
                site_name="Theme Redefine",
                is_active=True,
            )
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
            dispatch_uid="blog.create_default_site_config",
        )
        from . import signals  # noqa: F401
