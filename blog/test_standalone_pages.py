from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from .models import (
    CommentBadge,
    CommentBadgeTranslation,
    SiteConfiguration,
    StandalonePage,
    StandalonePageTranslation,
)


class StandalonePageTests(TestCase):
    def setUp(self):
        cache.clear()
        self.site = SiteConfiguration.objects.create(
            config_name="Pages",
            site_name="Pages",
            is_active=True,
        )

    def test_new_site_gets_one_setting_for_each_builtin_page(self):
        pages = StandalonePage.objects.filter(config=self.site).exclude(
            page_type=StandalonePage.CUSTOM
        )

        self.assertEqual(pages.count(), len(StandalonePage.BUILTIN_DEFAULTS))
        self.assertTrue(pages.get(page_type=StandalonePage.ARCHIVES).enabled)
        self.assertFalse(pages.get(page_type=StandalonePage.BOOKMARKS).enabled)

    def test_custom_page_renders_markdown_and_honours_visibility(self):
        page = StandalonePage.objects.create(
            config=self.site,
            page_type=StandalonePage.CUSTOM,
            title="About",
            slug="about",
            content="## Hello\n\nThis is **Django**.",
            enabled=False,
        )

        self.assertEqual(self.client.get("/about/").status_code, 404)
        page.enabled = True
        page.save(update_fields=("enabled", "updated_at"))
        response = self.client.get("/about/")

        self.assertContains(response, "<h1>About</h1>", html=True)
        self.assertContains(response, '<h2 id="hello">Hello</h2>', html=True)
        self.assertContains(response, "<strong>Django</strong>", html=True)

    def test_custom_page_rejects_application_routes(self):
        page = StandalonePage(
            config=self.site,
            title="Reserved",
            slug="comments",
        )
        with self.assertRaisesMessage(ValidationError, "reserved"):
            page.full_clean()

    def test_custom_page_uses_the_current_language_translation(self):
        page = StandalonePage.objects.create(
            config=self.site,
            title="About",
            slug="about",
            content="English body",
        )
        StandalonePageTranslation.objects.create(
            page=page,
            language_code="zh-hans",
            title="关于",
            content="**中文正文**",
        )

        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "zh-hans"
        with translation.override("zh-hans"):
            response = self.client.get("/about/")

        self.assertContains(response, "<h1>关于</h1>", html=True)
        self.assertContains(response, "<strong>中文正文</strong>", html=True)

    def test_builtin_page_uses_its_own_visibility_and_content(self):
        page = StandalonePage.objects.get(
            config=self.site, page_type=StandalonePage.FRIENDS
        )
        page.enabled = False
        page.content = "Hidden introduction"
        page.save()
        self.assertEqual(self.client.get(reverse("friends")).status_code, 404)

        page.enabled = True
        page.content = "**Friend introduction**"
        page.save()
        response = self.client.get(reverse("friends"))
        self.assertContains(response, "<strong>Friend introduction</strong>", html=True)

    def test_custom_page_supports_internal_comments(self):
        self.site.comment_enabled = True
        self.site.comment_system = "internal"
        self.site.comment_require_login = False
        self.site.comment_allow_guest = True
        self.site.save()
        page = StandalonePage.objects.create(
            config=self.site,
            title="Guestbook",
            slug="guestbook",
            comments_enabled=True,
        )

        response = self.client.get("/guestbook/")
        self.assertContains(response, 'data-comments-api-base="/api/page-comments/"')
        created = self.client.post(
            reverse("page_comment_create", args=(page.slug,)),
            {"content": "Hello page", "nickname": "Reader"},
        )
        self.assertEqual(created.status_code, 200)
        self.assertEqual(page.comments.get().content, "Hello page")
        listed = self.client.get(reverse("page_comment_list", args=(page.slug,)))
        self.assertContains(listed, "Hello page")


class OwnerBadgeTranslationAdminTests(TestCase):
    def setUp(self):
        cache.clear()
        self.site = SiteConfiguration.objects.create(
            config_name="Badges",
            site_name="Badges",
            is_active=True,
        )
        self.admin = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="A-strong-password-123",
        )
        self.client.force_login(self.admin)

    def test_owner_badge_uses_requested_default_translations(self):
        badge = CommentBadge.objects.create(
            config=self.site,
            name="博主",
            is_owner_badge=True,
        )

        names = dict(badge.translations.values_list("language_code", "name"))
        self.assertEqual(names["en"], "Blogger")
        self.assertEqual(names["es"], "Bloguero")
        self.assertEqual(names["fr"], "Blogueur")
        self.assertEqual(names["ja"], "ブロガー")
        self.assertEqual(names["zh-hans"], "博主")
        self.assertEqual(names["zh-hk"], "部落客")
        self.assertEqual(names["zh-tw"], "部落客")

    def test_admin_can_override_an_auto_created_language_without_server_error(self):
        response = self.client.post(
            reverse("admin:blog_commentbadge_add"),
            {
                "name": "Owner",
                "is_owner_badge": "on",
                "inherit_theme": "on",
                "admin_only": "on",
                "enabled": "on",
                "order": "0",
                "translations-TOTAL_FORMS": "1",
                "translations-INITIAL_FORMS": "0",
                "translations-MIN_NUM_FORMS": "0",
                "translations-MAX_NUM_FORMS": "1000",
                "translations-0-language_code": "zh-hans",
                "translations-0-name": "站点作者",
                "_save": "Save",
            },
        )

        self.assertEqual(response.status_code, 302)
        badge = CommentBadge.objects.get(config=self.site, is_owner_badge=True)
        self.assertEqual(
            CommentBadgeTranslation.objects.get(
                badge=badge, language_code="zh-hans"
            ).name,
            "站点作者",
        )
        self.assertEqual(badge.translations.count(), 7)

    def test_custom_badge_duplicate_language_is_a_form_error_not_server_error(self):
        badge = CommentBadge.objects.create(config=self.site, name="Helper")
        existing = CommentBadgeTranslation.objects.create(
            badge=badge,
            language_code="fr",
            name="Assistant",
        )
        response = self.client.post(
            reverse("admin:blog_commentbadge_change", args=(badge.pk,)),
            {
                "name": "Helper",
                "inherit_theme": "on",
                "enabled": "on",
                "order": "0",
                "translations-TOTAL_FORMS": "2",
                "translations-INITIAL_FORMS": "1",
                "translations-MIN_NUM_FORMS": "0",
                "translations-MAX_NUM_FORMS": "1000",
                "translations-0-id": str(existing.pk),
                "translations-0-badge": str(badge.pk),
                "translations-0-language_code": "fr",
                "translations-0-name": "Assistant",
                "translations-1-language_code": "fr",
                "translations-1-name": "Aide",
                "_save": "Save",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Each language can only be added once.")
        self.assertEqual(badge.translations.count(), 1)
