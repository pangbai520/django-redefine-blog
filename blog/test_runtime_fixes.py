import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import ArticleModel, SiteConfiguration, TrafficModel


class RuntimeRegressionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.site = SiteConfiguration.objects.create(
            config_name="Runtime fixes",
            site_name="Runtime Blog",
            colour_primary="#00bbfe",
            is_active=True,
            comment_enabled=True,
            comment_system="internal",
            comment_registration_enabled=True,
            comment_require_email_verification=True,
        )
        self.article = ArticleModel.objects.create(
            title="Counted article",
            slug="counted-article",
            content="Body",
            is_published=True,
        )

    def test_article_records_the_current_read_before_rendering(self):
        response = self.client.get(
            reverse("article", args=[self.article.slug]),
            HTTP_USER_AGENT="Mozilla/5.0 Real Browser",
            REMOTE_ADDR="192.0.2.40",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["article_pv"], 1)
        self.assertEqual(
            TrafficModel.objects.filter(path=self.article.get_absolute_url()).count(), 1
        )
        second = self.client.get(
            reverse("article", args=[self.article.slug]),
            HTTP_USER_AGENT="Mozilla/5.0 Real Browser",
            REMOTE_ADDR="192.0.2.40",
        )
        self.assertEqual(second.context["article_pv"], 1)

    @override_settings(TRAFFIC_REQUIRE_BROWSER_NAVIGATION=True)
    def test_production_traffic_requires_a_top_level_browser_navigation(self):
        self.client.get(
            "/", HTTP_USER_AGENT="Mozilla/5.0 Real Browser", REMOTE_ADDR="192.0.2.41"
        )
        self.assertFalse(TrafficModel.objects.exists())
        self.client.get(
            "/",
            HTTP_USER_AGENT="Mozilla/5.0 Real Browser",
            HTTP_SEC_FETCH_DEST="document",
            HTTP_SEC_FETCH_MODE="navigate",
            REMOTE_ADDR="192.0.2.41",
        )
        self.assertEqual(TrafficModel.objects.count(), 1)

    def test_saved_accent_overrides_each_compiled_theme_boundary(self):
        html = self.client.get("/").content.decode()
        self.assertIn("body.light-mode", html)
        self.assertIn("body.dark-mode", html)
        self.assertGreaterEqual(html.count("--primary-color: #00bbfe"), 3)

    def test_robots_txt_points_to_sitemap_and_hides_private_routes(self):
        response = self.client.get(reverse("robots_txt"), secure=True)
        text = response.content.decode()
        self.assertEqual(response["Content-Type"], "text/plain; charset=utf-8")
        self.assertIn("Disallow: /api/", text)
        self.assertIn("Disallow: /comments/", text)
        self.assertIn("Sitemap: https://testserver/sitemap.xml", text)

    def test_account_pages_are_noindex_and_not_counted_as_reader_traffic(self):
        response = self.client.get(
            reverse("comment_register"),
            HTTP_USER_AGENT="Mozilla/5.0 Real Browser",
            REMOTE_ADDR="192.0.2.42",
        )
        self.assertContains(response, '<meta name="robots" content="noindex,nofollow">')
        self.assertFalse(TrafficModel.objects.exists())

    def test_sitemap_includes_only_enabled_optional_pages(self):
        self.site.bookmarks_enabled = True
        self.site.essays_enabled = False
        self.site.masonry_enabled = False
        self.site.friends_enabled = False
        self.site.save(
            update_fields=(
                "bookmarks_enabled",
                "essays_enabled",
                "masonry_enabled",
                "friends_enabled",
            )
        )
        cache.clear()
        body = self.client.get("/sitemap.xml", secure=True).content.decode()
        self.assertIn("https://testserver/bookmarks/", body)
        self.assertNotIn("https://testserver/essays/", body)
        self.assertNotIn("https://testserver/masonry/", body)
        self.assertNotIn("https://testserver/friends/", body)
        self.assertEqual(self.client.get(reverse("friends")).status_code, 404)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_email_link_get_is_safe_from_mail_scanners_and_post_activates(self):
        response = self.client.post(
            reverse("comment_register"),
            {
                "username": "mail-reader",
                "email": "mail-reader@example.com",
                "password": "A-strong-password-123",
                "password_confirm": "A-strong-password-123",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        match = re.search(r"https?://[^\s]+/comments/verify/[^\s]+", mail.outbox[0].body)
        self.assertIsNotNone(match)
        verify_path = match.group(0).replace("http://testserver", "")
        first_scan = self.client.get(verify_path)
        self.assertContains(first_scan, "Confirm that you want to activate this account")
        user = get_user_model().objects.get(username="mail-reader")
        self.assertFalse(user.is_active)
        self.assertEqual(self.client.get(verify_path).status_code, 200)
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertEqual(self.client.post(verify_path).status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.is_active)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_verification_email_uses_request_language_and_site_accent(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "zh-hans"
        response = self.client.post(
            reverse("comment_register"),
            {
                "username": "translated-reader",
                "email": "translated-reader@example.com",
                "password": "A-strong-password-123",
                "password_confirm": "A-strong-password-123",
            },
        )
        self.assertEqual(response.status_code, 200)
        message = mail.outbox[0]
        self.assertIn("验证您的账号", message.subject)
        self.assertIn("#00bbfe", message.alternatives[0].content)
        self.assertIn("验证您的评论账号", message.alternatives[0].content)
