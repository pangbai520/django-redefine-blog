from django.core.management.base import BaseCommand

from blog.account_cleanup import cleanup_expired_unverified_accounts


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
        count, _deleted = cleanup_expired_unverified_accounts(
            hours=options["hours"]
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {count} expired unverified account(s)."
            )
        )
