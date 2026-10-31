import hashlib
import os
from pathlib import Path
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


DATABASE_URL = "https://raw.githubusercontent.com/lionsoul2014/ip2region/v3.18.0/data/ip2region_v4.xdb"
DATABASE_SHA256 = "8e31bbdccb5bf21028af10592d4312ec975da0bffa108c0c5d862a12190f9ad3"


class Command(BaseCommand):
    help = "Install the pinned offline IPv4 location database used by comments."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true")

    def handle(self, *args, **options):
        destination = Path(settings.IP2REGION_DB_V4)
        if destination.is_file() and not options["force"]:
            if self._sha256(destination) == DATABASE_SHA256:
                self.stdout.write(f"IP location database is current: {destination}")
                self._validate_lookup()
                return
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".download")
        request = Request(DATABASE_URL, headers={"User-Agent": "django-redefine-blog/deployment"})
        try:
            digest = hashlib.sha256()
            with urlopen(request, timeout=60) as response, temporary.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
                    digest.update(chunk)
            if digest.hexdigest() != DATABASE_SHA256:
                raise CommandError("Downloaded IP location database failed its SHA-256 check.")
            os.replace(temporary, destination)
            destination.chmod(0o644)
        finally:
            temporary.unlink(missing_ok=True)
        self.stdout.write(self.style.SUCCESS(f"Installed IP location database: {destination}"))
        self._validate_lookup()

    @staticmethod
    def _validate_lookup():
        from blog.ip_location import _searchers, get_ip_location

        _searchers.clear()
        get_ip_location.cache_clear()
        if not get_ip_location("183.251.202.251"):
            raise CommandError(
                "The IP database was installed, but py-ip2region could not resolve a test address. "
                "Install production dependencies before running this command."
            )

    @staticmethod
    def _sha256(path):
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()
