import hashlib
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import unquote

from django.conf import settings
from django.core.files import File
from django.core.files.storage import FileSystemStorage, default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from blog.models import (
    ArticleModel,
    Comment,
    StandalonePage,
    StandalonePageTranslation,
)
from blog.services.media_storage import clean_name, is_local, save_exact, walk_files


LOCAL_MEDIA_RE = re.compile(
    r"(?<![A-Za-z0-9])(?P<url>/resources/(?P<name>[^\s\"'<>)}\]\u3002"
    r"\uff0c\uff1b\uff01\uff1f]+))"
)
CONTENT_MODELS = (
    ArticleModel,
    Comment,
    StandalonePage,
    StandalonePageTranslation,
)


def digest_file(handle):
    digest = hashlib.sha256()
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.digest()


def rewrite_content(content, targets):
    replaced = 0

    def replace(match):
        nonlocal replaced
        try:
            name = clean_name(unquote(match.group("name")))
        except CommandError:
            return match.group("url")
        target = targets.get(name)
        if not target:
            return match.group("url")
        replaced += 1
        return target

    return LOCAL_MEDIA_RE.sub(replace, content or ""), replaced


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

        changed_rows = 0
        changed_urls = 0
        if rewrite_urls:
            targets = {}
            for path in copied:
                name = clean_name(path.relative_to(source).as_posix())
                target = default_storage.url(name)
                if not target.startswith(("http://", "https://")) or "?" in target:
                    raise CommandError(
                        "Media URLs must be stable public HTTP(S) URLs before content "
                        f"can be rewritten: {target}"
                    )
                targets[name] = target
            with transaction.atomic():
                for model in CONTENT_MODELS:
                    changed = []
                    for obj in model.objects.only("pk", "content").iterator(
                        chunk_size=200
                    ):
                        content, count = rewrite_content(obj.content, targets)
                        if not count:
                            continue
                        obj.content = content
                        changed.append(obj)
                        changed_urls += count
                    changed_rows += len(changed)
                    if changed and not options["dry_run"]:
                        model.objects.bulk_update(
                            changed,
                            ("content",),
                            batch_size=200,
                        )

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
                f"skipped {skipped} identical file(s); replaced {replaced} file(s); "
                f"rewrote {changed_urls} URL(s) in {changed_rows} content row(s)."
            )
        )
