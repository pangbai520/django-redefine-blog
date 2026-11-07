from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import translation

from blog.management.commands.install_ip_geolocation import (
    DATABASES,
    Command as InstallIpGeoCommand,
)
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
        self.assertContains(response, 'referrerpolicy="no-referrer"')

    def test_vote_switch(self):
        initial = self.client.get(self.url)
        self.assertEqual(initial.json(), {"counts": [0, 0, 0, 0, 0, 0], "active": None})
        self.assertNotIn("article_reaction_id", initial.cookies)

        first = self.client.post(
            self.url,
            data='{"index": 2}',
            content_type="application/json",
        )
        self.assertEqual(first.json(), {"counts": [0, 0, 1, 0, 0, 0], "active": 2})
        self.assertIn("article_reaction_id", first.cookies)

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
                reaction_order=index + 1 if index != 1 else None,
            )
        self.site.article_reaction_emoji_pack = pack
        self.site.save()

        response = self.client.get(reverse("article", args=[self.article.slug]))
        self.assertContains(response, "https://example.com/bili-0.png")
        self.assertNotContains(response, "https://example.com/bili-1.png")
        self.assertContains(response, "https://example.com/bili-2.png")
        self.assertNotContains(response, "tieba_agree.png")

        counts = self.client.get(self.url)
        self.assertEqual(counts.json()["counts"], [0, 0])
        invalid = self.client.post(
            self.url,
            data='{"index": 2}',
            content_type="application/json",
        )
        self.assertEqual(invalid.status_code, 400)

    def test_pack_scope(self):
        other = SiteConfiguration.objects.create(config_name="Other")
        pack = CommentEmojiPack.objects.create(config=other, name="Foreign")
        CommentEmoji.objects.create(
            pack=pack,
            name="Foreign emoji",
            image_url="https://example.com/foreign.png",
            reaction_order=1,
        )
        SiteConfiguration.objects.filter(pk=self.site.pk).update(
            article_reaction_emoji_pack=pack
        )
        cache.clear()

        response = self.client.get(reverse("article", args=[self.article.slug]))
        self.assertNotContains(response, "https://example.com/foreign.png")
        self.assertContains(response, "tieba_agree.png")

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

    def test_account_vote(self):
        user = get_user_model().objects.create_user(
            username="one-vote",
            password="not-used",
        )
        self.client.force_login(user)
        first = self.client.post(
            self.url,
            data='{"index": 0}',
            content_type="application/json",
        )
        self.assertEqual(first.json()["counts"], [1, 0, 0, 0, 0, 0])

        other = self.client_class()
        other.force_login(user)
        switched = other.post(
            self.url,
            data='{"index": 1}',
            content_type="application/json",
        )
        self.assertEqual(switched.json()["counts"], [0, 1, 0, 0, 0, 0])
        self.assertEqual(
            ArticleReactionVote.objects.filter(article=self.article, user=user).count(),
            1,
        )

    def test_request_guard(self):
        wrong_type = self.client.post(self.url, data={"index": 0})
        self.assertEqual(wrong_type.status_code, 415)

        oversized = self.client.post(
            self.url,
            data='{"index": 0, "padding": "' + ("x" * 1100) + '"}',
            content_type="application/json",
        )
        self.assertEqual(oversized.status_code, 413)

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

    def test_ip_version(self):
        parser = InstallIpGeoCommand().create_parser(
            "manage.py", "install_ip_geolocation"
        )

        self.assertEqual(parser.parse_args(["--ip-version", "6"]).ip_version, "6")

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
