from django.core.management.base import BaseCommand

from blog.portable_data import import_archive


class Command(BaseCommand):
    help = "Restore a ZIP created by export_blog."

    def add_arguments(self, parser):
        parser.add_argument("archive", help="Source .zip path")
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Replace existing blog rows before importing; unrelated project data is preserved.",
        )

    def handle(self, *args, **options):
        manifest = import_archive(options["archive"], options["replace"])
        self.stdout.write(
            self.style.SUCCESS(
                f"Import complete: {options['archive']} ({manifest['media_files']} media files)"
            )
        )
