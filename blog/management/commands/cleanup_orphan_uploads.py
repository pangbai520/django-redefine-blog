from datetime import timedelta

from django.apps import apps
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from django.db.models import FileField
from django.utils import timezone

from blog.models import CommentImage, EditorImage, EditorImageLease
from blog.services.editor_images import image_used, rebuild_refs
from blog.services.media_storage import walk_files


def referenced_files():
    names = set()
    for model in apps.get_models():
        for field in model._meta.fields:
            if not isinstance(field, FileField):
                continue
            values = (
                model._default_manager.exclude(**{field.name: ""})
                .values_list(field.name, flat=True)
                .iterator()
            )
            names.update(str(value) for value in values if value)
    return names


def old_storage_orphans(cutoff):
    references = referenced_files()
    seen = set()
    for prefix in settings.MEDIA_MANAGED_PREFIXES:
        for name in walk_files(default_storage, prefix):
            if name in seen or name in references:
                continue
            seen.add(name)
            try:
                modified = default_storage.get_modified_time(name)
            except (FileNotFoundError, NotImplementedError, OSError):
                continue
            if timezone.is_naive(modified):
                modified = timezone.make_aware(
                    modified,
                    timezone.get_current_timezone(),
                )
            if modified < cutoff:
                yield name


class Command(BaseCommand):
    help = "Delete unreferenced comment and article-editor images after a grace period."

    def add_arguments(self, parser):
        parser.add_argument(
            "--older-than-hours",
            type=int,
            default=24,
            help="Delete unattached comment images after this many hours (default: 24).",
        )
        parser.add_argument(
            "--draft-hours",
            type=int,
            default=72,
            help="Delete unsaved article images after this many hours (default: 72).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report matching rows without deleting files or database records.",
        )
        parser.add_argument(
            "--skip-storage-scan",
            action="store_true",
            help="Skip the final scan for untracked objects in managed media folders.",
        )

    def handle(self, *args, **options):
        hours = options["older_than_hours"]
        draft_hours = options["draft_hours"]
        if hours < 1 or draft_hours < 1:
            self.stderr.write(
                self.style.ERROR("Cleanup periods must be at least 1 hour.")
            )
            return
        comment_cutoff = timezone.now() - timedelta(hours=hours)
        draft_cutoff = timezone.now() - timedelta(hours=draft_hours)
        EditorImageLease.objects.filter(created_at__lt=draft_cutoff).delete()
        rebuild_refs()
        uploads = CommentImage.objects.filter(
            comment__isnull=True, created_at__lt=comment_cutoff
        )
        comment_count = uploads.count()
        editor_images = [
            image
            for image in EditorImage.objects.filter(
                refs__isnull=True, created_at__lt=draft_cutoff
            ).iterator()
            if not image_used(image)
        ]
        editor_count = len(editor_images)
        storage_orphans = (
            []
            if options["skip_storage_scan"]
            else list(old_storage_orphans(draft_cutoff))
        )
        storage_count = len(storage_orphans)
        if options["dry_run"]:
            self.stdout.write(
                f"{comment_count} comment image(s) and {editor_count} article "
                f"image(s), plus {storage_count} untracked storage object(s), "
                "would be deleted."
            )
            return
        for upload in uploads.iterator():
            upload.delete()
        for image in editor_images:
            image.delete()
        for name in storage_orphans:
            default_storage.delete(name)
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {comment_count} comment image(s) and "
                f"{editor_count} article image(s), plus {storage_count} "
                "untracked storage object(s)."
            )
        )
