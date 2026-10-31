import re
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone, translation
from django.template.loader import render_to_string

from .account_cleanup import CLEANUP_CACHE_KEY
from .image_cleanup import ORPHAN_IMAGE_CLEANUP_CACHE_KEY
from .ip_location import format_ip2region_result
from .models import (
    ArticleModel,
    CommentImage,
    PendingRegistration,
    SiteConfiguration,
    TrafficModel,
    UserProfile,
)


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
            TrafficModel.objects.filter(path=self.article.get_absolute_url()).count(),
            1,
        )
        self.article.refresh_from_db()
        self.assertEqual(self.article.view_count, 1)

        second = self.client.get(
            reverse("article", args=[self.article.slug]),
            HTTP_USER_AGENT="Mozilla/5.0 Real Browser",
            REMOTE_ADDR="192.0.2.40",
        )
        self.assertEqual(second.context["article_pv"], 1)
        self.article.refresh_from_db()
        self.assertEqual(self.article.view_count, 1)

    @override_settings(TRAFFIC_REQUIRE_BROWSER_NAVIGATION=True)
    def test_article_read_does_not_require_sec_fetch_headers(self):
        response = self.client.get(
            reverse("article", args=[self.article.slug]),
            HTTP_USER_AGENT="Mozilla/5.0 Mobile Privacy Browser",
            REMOTE_ADDR="192.0.2.43",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["article_pv"], 1)
        self.article.refresh_from_db()
        self.assertEqual(self.article.view_count, 1)

    def test_article_view_count_survives_traffic_retention_cleanup(self):
        self.client.get(
            reverse("article", args=[self.article.slug]),
            HTTP_USER_AGENT="Mozilla/5.0 Real Browser",
            REMOTE_ADDR="192.0.2.44",
        )
        TrafficModel.objects.all().delete()

        self.article.refresh_from_db()
        self.assertEqual(self.article.view_count, 1)

    def test_comment_location_prefers_region_and_falls_back_to_ip(self):
        user = self.site._meta.apps.get_model("auth", "User").objects.create_user(
            username="location-reader", password="A-strong-password-123"
        )
        comment = self.article.comments.create(
            author=user,
            content="Location",
            ip_address="183.251.202.251",
        )
        with patch("blog.comment_views.get_ip_location", return_value="福建三明"):
            response = self.client.get(
                reverse("comment_list", args=[self.article.slug])
            )
        self.assertEqual(response.json()["comments"][0]["ip_address"], "福建三明")

        with patch("blog.comment_views.get_ip_location", return_value=""):
            response = self.client.get(
                reverse("comment_list", args=[self.article.slug])
            )
        self.assertEqual(
            response.json()["comments"][0]["ip_address"],
            str(comment.ip_address),
        )

    def test_ip2region_chinese_location_is_compact(self):
        self.assertEqual(
            format_ip2region_result("中国|福建省|三明市|电信|CN"),
            "福建三明",
        )

    def test_swup_does_not_reuse_stale_pages(self):
        response = self.client.get("/")
        self.assertContains(response, "cache: false")
        self.assertContains(response, "data-site-revision=")

    @override_settings(TRAFFIC_REQUIRE_BROWSER_NAVIGATION=True)
    def test_production_traffic_requires_a_top_level_browser_navigation(self):
        self.client.get(
            "/",
            HTTP_USER_AGENT="Mozilla/5.0 Real Browser",
            REMOTE_ADDR="192.0.2.41",
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
        response = self.client.get("/")
        html = response.content.decode()

        self.assertIn("body.light-mode", html)
        self.assertIn("body.dark-mode", html)
        self.assertGreaterEqual(html.count("--primary-color: #00bbfe"), 3)
        self.assertIn("--selection-color: var(--primary-color)", html)
        self.assertIn("--waline-theme-color: var(--primary-color)", html)
        self.assertIn("--waline-active-color: var(--primary-color)", html)
        self.assertGreater(
            html.index('id="site-theme-overrides"'),
            html.index("css/style.css"),
        )

    def test_mobile_submenu_is_collapsed_until_its_toggle_is_used(self):
        css = (Path(__file__).parent / "static" / "css" / "style.css").read_text(
            encoding="utf-8"
        )

        self.assertIn("[data-target] {\n  display: none;", css)
        self.assertIn("[data-target]:not(.hidden) {\n  display: flex;", css)

    def test_footer_runtime_uses_thousands_separators(self):
        source = (
            Path(__file__).parent / "static" / "js" / "tools" / "runtime.js"
        ).read_text(encoding="utf-8")

        self.assertIn('new Intl.NumberFormat("en-US"', source)
        self.assertIn("runtimeNumberFormatter.format", source)
        footer = (
            Path(__file__).parent / "templates" / "components" / "footer" / "footer.html"
        ).read_text(encoding="utf-8")
        self.assertNotIn('class="odometer" id="runtime_days"', footer)
        scripts = (
            Path(__file__).parent / "templates" / "components" / "scripts.html"
        ).read_text(encoding="utf-8")
        self.assertNotIn("odometer.min.js", scripts)

    def test_bookmark_interactions_match_the_bundled_redefine_source(self):
        template = (
            Path(__file__).parent / "templates" / "pages" / "bookmarks" / "bookmarks.html"
        ).read_text(encoding="utf-8")
        css = (Path(__file__).parent / "static" / "css" / "style.css").read_text(
            encoding="utf-8"
        )

        self.assertIn("hover:scale-102 transition-all duration-200", template)
        self.assertIn("transition: all 200ms ease", css)
        self.assertIn("transform: scale(1.02)", css)
        self.assertIn("transition: all 300ms ease", css)
        self.assertIn("transform: translateY(-0.25rem)", css)
        self.assertIn("transform: scale(1.05)", css)

    def test_normal_page_traffic_cleans_old_orphan_images_once_daily(self):
        orphan = CommentImage.objects.create(image="comment-images/orphan-auto.png")
        CommentImage.objects.filter(pk=orphan.pk).update(
            created_at=timezone.now() - timedelta(hours=25)
        )
        cache.delete(ORPHAN_IMAGE_CLEANUP_CACHE_KEY)

        self.client.get(reverse("index"))

        self.assertFalse(CommentImage.objects.filter(pk=orphan.pk).exists())
        self.assertTrue(cache.get(ORPHAN_IMAGE_CLEANUP_CACHE_KEY))

    def test_robots_txt_points_to_sitemap_and_hides_private_routes(self):
        response = self.client.get(reverse("robots_txt"), secure=True)
        text = response.content.decode()

        self.assertEqual(response["Content-Type"], "text/plain; charset=utf-8")
        self.assertIn("User-agent: *", text)
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
        self.assertContains(first_scan, "mail-reader@example.com")
        self.assertContains(first_scan, "data-skip-preloader")
        user = self.site._meta.apps.get_model("auth", "User").objects.get(
            username="mail-reader"
        )
        self.assertFalse(user.is_active)
        self.assertTrue(PendingRegistration.objects.filter(user=user).exists())
        self.assertFalse(UserProfile.objects.filter(user=user).exists())

        second_scan = self.client.get(verify_path)
        self.assertEqual(second_scan.status_code, 200)
        user.refresh_from_db()
        self.assertFalse(user.is_active)

        activation = self.client.post(verify_path)
        self.assertEqual(activation.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertFalse(PendingRegistration.objects.filter(user=user).exists())
        self.assertTrue(UserProfile.objects.filter(user=user).exists())
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn("Welcome", mail.outbox[1].subject)

    @override_settings(UNVERIFIED_ACCOUNT_RETENTION_HOURS=1)
    def test_expired_unverified_registration_is_removed_lazily(self):
        User = self.site._meta.apps.get_model("auth", "User")
        user = User.objects.create_user(
            username="abandoned-reader",
            email="abandoned@example.com",
            password="A-strong-password-123",
            is_active=False,
        )
        pending = PendingRegistration.objects.create(user=user)
        PendingRegistration.objects.filter(pk=pending.pk).update(
            created_at=timezone.now() - timedelta(hours=2)
        )
        cache.delete(CLEANUP_CACHE_KEY)

        self.client.get(reverse("comment_register"))

        self.assertFalse(User.objects.filter(pk=user.pk).exists())

    @override_settings(UNVERIFIED_ACCOUNT_RETENTION_HOURS=1)
    def test_expired_unverified_registration_is_removed_during_normal_page_traffic(self):
        User = self.site._meta.apps.get_model("auth", "User")
        user = User.objects.create_user(
            username="abandoned-home-reader",
            email="abandoned-home@example.com",
            password="A-strong-password-123",
            is_active=False,
        )
        pending = PendingRegistration.objects.create(user=user)
        PendingRegistration.objects.filter(pk=pending.pk).update(
            created_at=timezone.now() - timedelta(hours=2)
        )
        cache.delete(CLEANUP_CACHE_KEY)

        self.client.get(reverse("index"))

        self.assertFalse(User.objects.filter(pk=user.pk).exists())

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_welcome_email_uses_the_language_that_verified_the_account(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "zh-hans"
        self.client.post(
            reverse("comment_register"),
            {
                "username": "welcome-reader",
                "email": "welcome-reader@example.com",
                "password": "A-strong-password-123",
                "password_confirm": "A-strong-password-123",
            },
        )
        verify_url = re.search(
            r"https?://[^\s]+/comments/verify/[^\s]+", mail.outbox[0].body
        ).group(0)

        self.client.post(verify_url.replace("http://testserver", ""))

        self.assertEqual(len(mail.outbox), 2)
        self.assertIn("欢迎加入", mail.outbox[1].subject)
        self.assertIn("您的电子邮箱已验证", mail.outbox[1].body)
        self.assertIn("访问网站", mail.outbox[1].alternatives[0].content)

    def test_welcome_email_has_real_translations_for_every_supported_locale(self):
        User = self.site._meta.apps.get_model("auth", "User")
        user = User(username="localized-reader")
        expected = {
            "es": "Te damos la bienvenida",
            "fr": "Bienvenue",
            "ja": "ようこそ",
            "zh-hans": "欢迎",
            "zh-hk": "歡迎",
            "zh-tw": "歡迎",
        }
        for language_code, phrase in expected.items():
            with self.subTest(language_code=language_code), translation.override(language_code):
                rendered = render_to_string(
                    "emails/welcome.html",
                    {
                        "language_code": language_code,
                        "site": self.site,
                        "site_url": "https://example.com/",
                        "user": user,
                    },
                )
                self.assertIn(phrase, rendered)

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

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_password_reset_email_uses_request_language_and_site_accent(self):
        user = self.site._meta.apps.get_model("auth", "User").objects.create_user(
            username="reset-reader",
            email="reset-reader@example.com",
            password="A-strong-password-123",
        )
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "zh-hans"

        response = self.client.post(
            reverse("password_reset"),
            {"email": user.email},
        )

        self.assertEqual(response.status_code, 302)
        message = mail.outbox[0]
        self.assertIn("重置密码", message.subject)
        self.assertIn("#00bbfe", message.alternatives[0].content)
        self.assertIn("设置新密码", message.alternatives[0].content)
