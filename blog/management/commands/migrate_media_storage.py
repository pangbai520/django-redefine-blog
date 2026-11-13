import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError

from blog.services.media_migration import (
    file_digest,
    prepare_local_media,
    rewrite_database,
)
from blog.services.media_storage import is_local, save_exact


class Command(BaseCommand):
    help = (
        "Copy MEDIA_ROOT into the configured storage and rewrite verified legacy "
        "media URLs. Local source files are kept unless --delete-local is used."
    )

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
        parser.add_argument(
            "--skip-url-rewrite",
            action="store_true",
            help="Copy objects without rewriting legacy /resources/ URLs in content.",
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
        rewrite_urls = not options["skip_url_rewrite"]
        if rewrite_urls and not settings.MEDIA_PUBLIC_BASE_URL:
            raise CommandError(
                "MEDIA_PUBLIC_BASE_URL is required for automatic URL rewriting. "
                "Set it or use --skip-url-rewrite."
            )

        path_map, uploads, cleanup = prepare_local_media(
            source,
            dry_run=options["dry_run"],
        )
        copied = []
        skipped = 0
        replaced = 0
        for name, path in uploads.items():
            exists = default_storage.exists(name)
            if exists:
                with path.open("rb") as local, default_storage.open(name, "rb") as remote:
                    identical = file_digest(local) == file_digest(remote)
                if identical:
                    skipped += 1
                    copied.append(name)
                    continue
                if not options["replace"]:
                    raise CommandError(
                        f"Target object differs: {name}. Use --replace after checking it."
                    )
                replaced += 1
            if options["dry_run"]:
                copied.append(name)
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
            copied.append(name)

        targets = {}
        if rewrite_urls:
            for old_name, new_name in path_map.items():
                if new_name not in copied:
                    continue
                target = default_storage.url(new_name)
                if not target.startswith(("http://", "https://")) or "?" in target:
                    raise CommandError(
                        "Media URLs must be stable public HTTP(S) URLs before content "
                        f"can be rewritten: {target}"
                    )
                targets[old_name] = target
        changed_refs, changed_rows, changed_urls = rewrite_database(
            path_map,
            targets,
            rewrite_urls=rewrite_urls,
            dry_run=options["dry_run"],
        )

        if options["delete_local"] and not options["dry_run"]:
            for path in cleanup:
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
                f"skipped {skipped} identical file(s); replaced {replaced} file(s); "
                f"updated {changed_refs} stored file reference(s); rewrote "
                f"{changed_urls} URL(s) in {changed_rows} content row(s)."
            )
        )
