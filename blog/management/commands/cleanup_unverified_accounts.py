from django.core.management.base import BaseCommand

from blog.services.accounts import clean_unverified


class Command(BaseCommand):
    help = "Delete expired accounts that never completed email verification."

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours",
            type=int,
            default=None,
            help="Override the configured retention period in hours.",
        )

    def handle(self, *args, **options):
        count, _deleted = clean_unverified(hours=options["hours"])
        self.stdout.write(
            self.style.SUCCESS(f"Deleted {count} expired unverified account(s).")
        )
