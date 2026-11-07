from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from blog.models import CommentImage, EditorImage, EditorImageLease
from blog.services.editor_images import image_used, rebuild_refs


class Command(BaseCommand):
    help = "Delete unreferenced comment and article-editor images after a grace period."

    def add_arguments(self, parser):
        parser.add_argument(
            "--older-than-hours",
            type=int,
            default=24,
            help="Only inspect unattached images older than this many hours (default: 24).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report matching rows without deleting files or database records.",
        )

    def handle(self, *args, **options):
        hours = options["older_than_hours"]
        if hours < 1:
            self.stderr.write(
                self.style.ERROR("--older-than-hours must be at least 1.")
            )
            return
        cutoff = timezone.now() - timedelta(hours=hours)
        EditorImageLease.objects.filter(created_at__lt=cutoff).delete()
        rebuild_refs()
        uploads = CommentImage.objects.filter(
            comment__isnull=True, created_at__lt=cutoff
        )
        comment_count = uploads.count()
        editor_images = [
            image
            for image in EditorImage.objects.filter(
                refs__isnull=True, created_at__lt=cutoff
            ).iterator()
            if not image_used(image)
        ]
        editor_count = len(editor_images)
        if options["dry_run"]:
            self.stdout.write(
                f"{comment_count} comment image(s) and {editor_count} article "
                "image(s) would be deleted."
            )
            return
        for upload in uploads.iterator():
            upload.delete()
        for image in editor_images:
            image.delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {comment_count} comment image(s) and "
                f"{editor_count} article image(s)."
            )
        )
