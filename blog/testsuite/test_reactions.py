from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import translation

from blog.management.commands.install_ip_geolocation import DATABASES
from blog.models import (
    ArticleModel,
    ArticleReactionVote,
    CommentEmoji,
    CommentEmojiPack,
    SiteConfiguration,
)
from blog.services.geo import get_ip_location


class ArticleReactionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.site = SiteConfiguration.objects.create(
            config_name="Reactions",
            is_active=True,
            article_reaction_enabled=True,
        )
        self.article = ArticleModel.objects.create(
            title="Reaction post",
            slug="reaction-post",
            content="Body",
            is_published=True,
        )
        self.url = reverse("article_reactions", args=[self.article.slug])

    def test_reaction_markup(self):
        with translation.override("en"):
            response = self.client.get(reverse("article", args=[self.article.slug]))

        self.assertContains(response, 'class="wl-reaction"')
        self.assertContains(response, "tieba_agree.png")
        self.assertContains(response, "tieba_sleep.png")
        self.assertContains(response, "What do you think?")

    def test_vote_switch(self):
        initial = self.client.get(self.url)
        self.assertEqual(initial.json(), {"counts": [0, 0, 0, 0, 0, 0], "active": None})
        self.assertIn("article_reaction_id", initial.cookies)

        first = self.client.post(
            self.url,
            data='{"index": 2}',
            content_type="application/json",
        )
        self.assertEqual(first.json(), {"counts": [0, 0, 1, 0, 0, 0], "active": 2})

        switched = self.client.post(
            self.url,
            data='{"index": 4}',
            content_type="application/json",
        )
        self.assertEqual(switched.json(), {"counts": [0, 0, 0, 0, 1, 0], "active": 4})

        cancelled = self.client.post(
            self.url,
            data='{"index": 4}',
            content_type="application/json",
        )
        self.assertEqual(cancelled.json(), {"counts": [0, 0, 0, 0, 0, 0], "active": None})
        self.assertFalse(ArticleReactionVote.objects.exists())

    def test_pack_customization(self):
        pack = CommentEmojiPack.objects.create(
            config=self.site,
            name="Bilibili",
        )
        for index in range(3):
            CommentEmoji.objects.create(
                pack=pack,
                name=f"Bili {index}",
                image_url=f"https://example.com/bili-{index}.png",
                order=index,
            )
        self.site.article_reaction_emoji_pack = pack
        self.site.article_reaction_limit = 2
        self.site.save()

        response = self.client.get(reverse("article", args=[self.article.slug]))
        self.assertContains(response, "https://example.com/bili-0.png")
        self.assertContains(response, "https://example.com/bili-1.png")
        self.assertNotContains(response, "https://example.com/bili-2.png")
        self.assertNotContains(response, "tieba_agree.png")

        counts = self.client.get(self.url)
        self.assertEqual(counts.json()["counts"], [0, 0])
        invalid = self.client.post(
            self.url,
            data='{"index": 2}',
            content_type="application/json",
        )
        self.assertEqual(invalid.status_code, 400)

    def test_vote_audit(self):
        user = get_user_model().objects.create_user(
            username="reaction-user",
            password="not-used",
        )
        self.client.force_login(user)
        self.client.get(self.url)
        self.client.post(
            self.url,
            data='{"index": 1}',
            content_type="application/json",
            REMOTE_ADDR="2001:db8::42",
            HTTP_USER_AGENT="Reaction browser",
        )

        vote = ArticleReactionVote.objects.get()
        self.assertEqual(vote.user, user)
        self.assertEqual(vote.ip_address, "2001:db8::42")
        self.assertEqual(vote.user_agent, "Reaction browser")

    def test_browser_counts(self):
        self.client.get(self.url)
        self.client.post(self.url, data='{"index": 0}', content_type="application/json")

        other = self.client_class()
        other.get(self.url)
        response = other.post(
            self.url,
            data='{"index": 0}',
            content_type="application/json",
        )

        self.assertEqual(response.json()["counts"], [2, 0, 0, 0, 0, 0])

    def test_invalid_reaction(self):
        self.client.get(self.url)
        invalid = self.client.post(
            self.url,
            data='{"index": 6}',
            content_type="application/json",
        )
        self.assertEqual(invalid.status_code, 400)

        self.article.show_reaction = False
        self.article.save(update_fields=("show_reaction",))
        self.assertEqual(self.client.get(self.url).status_code, 404)


class IpDatabaseTests(SimpleTestCase):
    def tearDown(self):
        get_ip_location.cache_clear()

    def test_ipv6_database(self):
        self.assertEqual(Path(settings.IP2REGION_DB_V6).name, "ip2region_v6.xdb")
        self.assertEqual(len(DATABASES[6]["sha256"]), 64)

    def test_ipv6_searcher(self):
        searcher = type(
            "Searcher",
            (),
            {"search": staticmethod(lambda _address: "中国|甲省|乙市|电信|CN")},
        )()
        with patch("blog.services.geo._get_searcher", return_value=searcher) as mocked:
            location = get_ip_location("2001:4860:4860::8888")

        mocked.assert_called_once_with(6)
        self.assertEqual(location, "甲乙")
