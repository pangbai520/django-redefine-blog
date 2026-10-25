from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from blog.demo_content import create_demo_content


class Command(BaseCommand):
    help = "Create the optional Django Redefine demo site."

    def add_arguments(self, parser):
        parser.add_argument(
            "--update-existing",
            action="store_true",
            help="Apply the demo settings to an existing site configuration.",
        )

    def handle(self, *args, **options):
        owner = get_user_model().objects.filter(is_superuser=True).order_by("pk").first()
        if owner is None:
            raise CommandError(
                "Create a superuser first with: python manage.py createsuperuser"
            )
        created = create_demo_content(
            owner=owner,
            update_existing=options["update_existing"],
        )
        if created:
            self.stdout.write(self.style.SUCCESS("Demo site created."))
        else:
            self.stdout.write(
                "A site configuration already exists; nothing changed. "
                "Use --update-existing only if you want to apply the demo settings to it."
            )
