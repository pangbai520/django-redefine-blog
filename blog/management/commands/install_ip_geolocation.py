import hashlib
import os
from pathlib import Path
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

DATABASES = {
    4: {
        "setting": "IP2REGION_DB_V4",
        "url": (
            "https://raw.githubusercontent.com/lionsoul2014/ip2region/"
            "v3.18.0/data/ip2region_v4.xdb"
        ),
        "sha256": "8e31bbdccb5bf21028af10592d4312ec975da0bffa108c0c5d862a12190f9ad3",
        "test_ip": "8.8.8.8",
    },
    6: {
        "setting": "IP2REGION_DB_V6",
        "url": (
            "https://raw.githubusercontent.com/lionsoul2014/ip2region/"
            "v3.18.0/data/ip2region_v6.xdb"
        ),
        "sha256": "939f6b46bd2b8bec3cf7c5ceb8ba782266ae9b1f35b5ba7916700dec0b7506ed",
        "test_ip": "2408:8266:100:1000::",
    },
}


class Command(BaseCommand):
    help = "Install the pinned offline IPv4 and IPv6 location databases used by comments."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true")
        parser.add_argument(
            "--version",
            choices=("all", "4", "6"),
            default="all",
            help="Install both databases or only one address family.",
        )

    def handle(self, *args, **options):
        selected = options["version"]
        versions = (4, 6) if selected == "all" else (int(selected),)
        for version in versions:
            self._install(version, force=options["force"])

    def _install(self, version, *, force):
        spec = DATABASES[version]
        destination = Path(getattr(settings, spec["setting"]))
        if destination.is_file() and not force:
            if self._sha256(destination) == spec["sha256"]:
                self.stdout.write(
                    f"IPv{version} location database is current: {destination}"
                )
                self._validate_lookup(version, spec["test_ip"])
                return

        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".download")
        request = Request(
            spec["url"], headers={"User-Agent": "django-redefine-blog/deployment"}
        )

        try:
            digest = hashlib.sha256()
            with urlopen(request, timeout=120) as response, temporary.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
                    digest.update(chunk)

            if digest.hexdigest() != spec["sha256"]:
                raise CommandError(
                    f"Downloaded IPv{version} location database failed its SHA-256 check."
                )

            os.replace(temporary, destination)
            destination.chmod(0o644)
        finally:
            temporary.unlink(missing_ok=True)

        self.stdout.write(
            self.style.SUCCESS(
                f"Installed IPv{version} location database: {destination}"
            )
        )
        self._validate_lookup(version, spec["test_ip"])

    @staticmethod
    def _validate_lookup(version, address):
        from blog.services.geo import _searchers, get_ip_location

        _searchers.pop(version, None)
        get_ip_location.cache_clear()
        if not get_ip_location(address):
            raise CommandError(
                f"The IPv{version} database was installed, but py-ip2region could not "
                "resolve its test address. Install production dependencies before "
                "running this command."
            )

    @staticmethod
    def _sha256(path):
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()
