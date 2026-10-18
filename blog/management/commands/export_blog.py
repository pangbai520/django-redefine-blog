from django.core.management.base import BaseCommand, CommandError

from blog.portable_data import export_archive


class Command(BaseCommand):
    help = "Export blog content, accounts, configuration and uploaded files to a ZIP archive."

    def add_arguments(self, parser):
        parser.add_argument("output", help="Destination .zip path")
        parser.add_argument(
            "--include-traffic",
            action="store_true",
            help="Include traffic records, which may make the archive much larger.",
        )

    def handle(self, *args, **options):
        if not options["output"].lower().endswith(".zip"):
            raise CommandError("The export destination must use the .zip extension.")
        manifest = export_archive(options["output"], options["include_traffic"])
        self.stdout.write(
            self.style.SUCCESS(
                f"Export complete: {options['output']} ({manifest['media_files']} media files)"
            )
        )
