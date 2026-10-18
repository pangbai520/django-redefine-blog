from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from blog.portable_data import export_archive


class Command(BaseCommand):
    help = "Create a timestamped portable backup and prune older automatic backups."

    def add_arguments(self, parser):
        parser.add_argument("--directory", default=str(settings.BASE_DIR / "backups"), help="Backup destination directory (default: BASE_DIR/backups).")
        parser.add_argument("--keep", type=int, default=14, help="Number of automatic backups to retain (default: 14).")
        parser.add_argument("--include-traffic", action="store_true", help="Include traffic records, which may make the archive much larger.")

    def handle(self, *args, **options):
        keep = options["keep"]
        if keep < 1:
            raise CommandError("--keep must be at least 1.")
        destination = Path(options["directory"]).expanduser().resolve()
        destination.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
        archive = destination / f"blog-backup-{stamp}.zip"
        manifest = export_archive(str(archive), options["include_traffic"])
        backups = sorted(destination.glob("blog-backup-*.zip"), key=lambda path: path.stat().st_mtime, reverse=True)
        for old_backup in backups[keep:]:
            old_backup.unlink()
        self.stdout.write(self.style.SUCCESS(f"Backup complete: {archive} ({manifest['media_files']} media files)"))
