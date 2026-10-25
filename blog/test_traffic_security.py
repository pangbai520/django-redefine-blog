from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from .models import TrafficModel


class TrafficSecurityTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_repeated_page_views_are_deduplicated_in_the_shared_cache(self):
        headers = {
            "HTTP_USER_AGENT": "Mozilla/5.0 Real Browser",
            "REMOTE_ADDR": "192.0.2.90",
        }

        self.client.get("/", **headers)
        self.client.get("/", **headers)

        self.assertEqual(TrafficModel.objects.filter(path="/").count(), 1)

    @override_settings(TRAFFIC_RETENTION_DAYS=30)
    def test_old_traffic_is_removed_during_daily_cleanup(self):
        old = TrafficModel.objects.create(
            path="/old/",
            ip="192.0.2.91",
            user_agent="Browser",
        )
        TrafficModel.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=31)
        )

        self.client.get(
            "/",
            HTTP_USER_AGENT="Mozilla/5.0 Real Browser",
            REMOTE_ADDR="192.0.2.92",
        )

        self.assertFalse(TrafficModel.objects.filter(pk=old.pk).exists())
