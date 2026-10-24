from django.core.management.base import BaseCommand

from blog.cache_utils import bump_cache_version
from blog.search import rebuild_search_index


class Command(BaseCommand):
    help = "Rebuild article search documents and the database-native search index."

    def handle(self, *args, **options):
        count, backend = rebuild_search_index()
        bump_cache_version("search")
        self.stdout.write(
            self.style.SUCCESS(f"Indexed {count} articles using {backend}.")
        )
