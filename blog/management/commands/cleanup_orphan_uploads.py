from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from blog.models import CommentImage


class Command(BaseCommand):
    help = "Delete comment images that were uploaded but never attached to a comment."

    def add_arguments(self, parser):
        parser.add_argument("--older-than-hours", type=int, default=24, help="Only inspect unattached images older than this many hours (default: 24).")
        parser.add_argument("--dry-run", action="store_true", help="Report matching rows without deleting files or database records.")

    def handle(self, *args, **options):
        hours = options["older_than_hours"]
        if hours < 1:
            self.stderr.write(self.style.ERROR("--older-than-hours must be at least 1."))
            return
        cutoff = timezone.now() - timedelta(hours=hours)
        uploads = CommentImage.objects.filter(comment__isnull=True, created_at__lt=cutoff)
        count = uploads.count()
        if options["dry_run"]:
            self.stdout.write(f"{count} orphaned comment image(s) would be deleted.")
            return
        for upload in uploads.iterator():
            upload.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {count} orphaned comment image(s)."))
