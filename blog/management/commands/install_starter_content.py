from django.core.management.base import BaseCommand

from blog.starter_content import install_starter_content


class Command(BaseCommand):
    help = "Install the public starter site, navigation, article and comment presets."

    def add_arguments(self, parser):
        parser.add_argument(
            "--update-existing",
            action="store_true",
            help="Apply the starter settings to the active configuration as well.",
        )

    def handle(self, *args, **options):
        installed = install_starter_content(
            update_existing=options["update_existing"],
        )
        if installed:
            self.stdout.write(self.style.SUCCESS("Starter content installed."))
        else:
            self.stdout.write("A site configuration already exists; nothing changed.")
