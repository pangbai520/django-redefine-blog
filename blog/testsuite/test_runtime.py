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

from ..services.accounts import CLEANUP_CACHE_KEY
from ..services.images import ORPHAN_IMAGE_CLEANUP_CACHE_KEY
from ..services.geo import format_ip2region_result
from ..models import (
    ArticleModel,
    CommentImage,
    PendingRegistration,
    SiteConfiguration,
    StandalonePage,
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

    def test_article_rendering(self):
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
    def test_article_headers(self):
        response = self.client.get(
            reverse("article", args=[self.article.slug]),
            HTTP_USER_AGENT="Mozilla/5.0 Mobile Privacy Browser",
            REMOTE_ADDR="192.0.2.43",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["article_pv"], 1)
        self.article.refresh_from_db()
        self.assertEqual(self.article.view_count, 1)

    def test_article_cleanup(self):
        self.client.get(
            reverse("article", args=[self.article.slug]),
            HTTP_USER_AGENT="Mozilla/5.0 Real Browser",
            REMOTE_ADDR="192.0.2.44",
        )
        TrafficModel.objects.all().delete()

        self.article.refresh_from_db()
        self.assertEqual(self.article.view_count, 1)

    def test_comment_ip(self):
        user = self.site._meta.apps.get_model("auth", "User").objects.create_user(
            username="location-reader", password="A-strong-password-123"
        )
        comment = self.article.comments.create(
            author=user,
            content="Location",
            ip_address="203.0.113.45",
        )
        with patch("blog.comment_views.get_ip_location", return_value="甲省乙市"):
            response = self.client.get(
                reverse("comment_list", args=[self.article.slug])
            )
        self.assertEqual(response.json()["comments"][0]["ip_address"], "甲省乙市")

        with patch("blog.comment_views.get_ip_location", return_value=""):
            response = self.client.get(
                reverse("comment_list", args=[self.article.slug])
            )
        self.assertEqual(
            response.json()["comments"][0]["ip_address"],
            str(comment.ip_address),
        )

    def test_ip2region_compact(self):
        self.assertEqual(
            format_ip2region_result("中国|甲省|乙市|电信|CN"),
            "甲乙",
        )

    def test_swup_pages(self):
        response = self.client.get("/")
        self.assertContains(response, "cache: false")
        self.assertContains(response, "data-site-revision=")

    @override_settings(TRAFFIC_REQUIRE_BROWSER_NAVIGATION=True)
    def test_production_navigation(self):
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

    def test_saved_boundary(self):
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

    def test_mobile_used(self):
        css = (Path(__file__).parent.parent / "static" / "css" / "style.css").read_text(
            encoding="utf-8"
        )

        self.assertIn("[data-target] {\n  display: none;", css)
        self.assertIn("[data-target]:not(.hidden) {\n  display: flex;", css)

    def test_footer_separators(self):
        source = (
            Path(__file__).parent.parent / "static" / "js" / "tools" / "runtime.js"
        ).read_text(encoding="utf-8")

        self.assertIn('new Intl.NumberFormat("en-US"', source)
        self.assertIn("runtimeNumberFormatter.format", source)
        footer = (
            Path(__file__).parent.parent
            / "templates"
            / "components"
            / "footer"
            / "footer.html"
        ).read_text(encoding="utf-8")
        self.assertNotIn('class="odometer" id="runtime_days"', footer)
        scripts = (
            Path(__file__).parent.parent / "templates" / "components" / "scripts.html"
        ).read_text(encoding="utf-8")
        self.assertNotIn("odometer.min.js", scripts)

    def test_bookmark_source(self):
        template = (
            Path(__file__).parent.parent
            / "templates"
            / "pages"
            / "bookmarks"
            / "bookmarks.html"
        ).read_text(encoding="utf-8")
        css = (Path(__file__).parent.parent / "static" / "css" / "style.css").read_text(
            encoding="utf-8"
        )
        controller = (
            Path(__file__).parent.parent
            / "static"
            / "js"
            / "layouts"
            / "bookmarkNav.js"
        ).read_text(encoding="utf-8")

        self.assertIn("hover:scale-102 transition-all duration-200", template)
        self.assertIn(".bookmark-nav-item.active", css)
        self.assertIn("background-color: var(--second-background-color)", css)
        self.assertIn("transform: scale(1.02)", css)
        self.assertNotIn(".bookmarks-page .bookmark-card-link:hover", css)
        self.assertIn('item.classList.toggle(\n                "active"', controller)

    def test_normal_daily(self):
        orphan = CommentImage.objects.create(image="comment-images/orphan-auto.png")
        CommentImage.objects.filter(pk=orphan.pk).update(
            created_at=timezone.now() - timedelta(hours=25)
        )
        cache.delete(ORPHAN_IMAGE_CLEANUP_CACHE_KEY)

        self.client.get(reverse("index"))

        self.assertFalse(CommentImage.objects.filter(pk=orphan.pk).exists())
        self.assertTrue(cache.get(ORPHAN_IMAGE_CLEANUP_CACHE_KEY))

    def test_robots_routes(self):
        response = self.client.get(reverse("robots_txt"), secure=True)
        text = response.content.decode()

        self.assertEqual(response["Content-Type"], "text/plain; charset=utf-8")
        self.assertIn("User-agent: *", text)
        self.assertIn("Disallow: /api/", text)
        self.assertIn("Disallow: /comments/", text)
        self.assertIn("Sitemap: https://testserver/sitemap.xml", text)

    def test_account_traffic(self):
        response = self.client.get(
            reverse("comment_register"),
            HTTP_USER_AGENT="Mozilla/5.0 Real Browser",
            REMOTE_ADDR="192.0.2.42",
        )

        self.assertContains(response, '<meta name="robots" content="noindex,nofollow">')
        self.assertFalse(TrafficModel.objects.exists())

    def test_sitemap_pages(self):
        StandalonePage.objects.filter(config=self.site).update(enabled=False)
        StandalonePage.objects.filter(
            config=self.site, page_type=StandalonePage.BOOKMARKS
        ).update(enabled=True)
        StandalonePage.objects.create(
            config=self.site,
            page_type=StandalonePage.CUSTOM,
            title="About",
            slug="about",
            enabled=True,
        )
        cache.clear()

        body = self.client.get("/sitemap.xml", secure=True).content.decode()

        self.assertIn("https://testserver/bookmarks/", body)
        self.assertNotIn("https://testserver/essays/", body)
        self.assertNotIn("https://testserver/masonry/", body)
        self.assertNotIn("https://testserver/friends/", body)
        self.assertIn("https://testserver/about/", body)
        self.assertEqual(self.client.get(reverse("friends")).status_code, 404)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_email_activates(self):
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
        match = re.search(
            r"https?://[^\s]+/comments/verify/[^\s]+", mail.outbox[0].body
        )
        self.assertIsNotNone(match)
        verify_path = match.group(0).replace("http://testserver", "")

        first_scan = self.client.get(verify_path)
        self.assertContains(
            first_scan, "Confirm that you want to activate this account"
        )
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
    def test_expired_lazily(self):
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
    def test_expired_traffic(self):
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
    def test_welcome_account(self):
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

    def test_welcome_locale(self):
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
            with self.subTest(language_code=language_code), translation.override(
                language_code
            ):
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
    def test_verification_accent(self):
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
    def test_password_accent(self):
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
