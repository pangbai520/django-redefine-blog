import hashlib
import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.files.storage import FileSystemStorage, default_storage
from django.core.management.base import BaseCommand, CommandError

from blog.services.media_storage import is_local, save_exact, walk_files


def digest_file(handle):
    digest = hashlib.sha256()
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.digest()


class Command(BaseCommand):
    help = "Copy existing MEDIA_ROOT files into the configured media storage."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            default=str(settings.MEDIA_ROOT),
            help="Local media directory to copy (default: MEDIA_ROOT).",
        )
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Replace a target object when its content differs.",
        )
        parser.add_argument(
            "--delete-local",
            action="store_true",
            help="Delete copied local files only after the complete migration succeeds.",
        )
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        source = Path(options["source"]).expanduser().resolve()
        if not source.is_dir():
            raise CommandError(f"Media source does not exist: {source}")
        if is_local(default_storage):
            target = Path(default_storage.location).resolve()
            if target == source:
                raise CommandError("The configured media storage is the source directory.")

        source_storage = FileSystemStorage(location=source)
        files = [source / name for name in sorted(walk_files(source_storage))]
        copied = []
        skipped = 0
        replaced = 0
        for path in files:
            name = path.relative_to(source).as_posix()
            exists = default_storage.exists(name)
            if exists:
                with path.open("rb") as local, default_storage.open(name, "rb") as remote:
                    identical = digest_file(local) == digest_file(remote)
                if identical:
                    skipped += 1
                    copied.append(path)
                    continue
                if not options["replace"]:
                    raise CommandError(
                        f"Target object differs: {name}. Use --replace after checking it."
                    )
                replaced += 1
            if options["dry_run"]:
                copied.append(path)
                continue
            previous = None
            if exists:
                previous = tempfile.TemporaryFile()
                with default_storage.open(name, "rb") as remote:
                    shutil.copyfileobj(remote, previous, length=1024 * 1024)
                previous.seek(0)
                default_storage.delete(name)
            try:
                with path.open("rb") as handle:
                    save_exact(default_storage, name, File(handle, name=name))
            except Exception:
                if previous is not None:
                    default_storage.delete(name)
                    save_exact(default_storage, name, File(previous, name=name))
                raise
            finally:
                if previous is not None:
                    previous.close()
            copied.append(path)

        if options["delete_local"] and not options["dry_run"]:
            for path in copied:
                path.unlink(missing_ok=True)
            for folder in sorted(source.rglob("*"), reverse=True):
                if folder.is_dir():
                    try:
                        folder.rmdir()
                    except OSError:
                        pass

        action = "Would copy" if options["dry_run"] else "Copied"
        self.stdout.write(
            self.style.SUCCESS(
                f"{action} {len(copied) - skipped} file(s); "
                f"skipped {skipped} identical file(s); replaced {replaced} file(s)."
            )
        )
