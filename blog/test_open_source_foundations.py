import ast
from gettext import GNUTranslations
from pathlib import Path
import re
from unittest.mock import Mock

from django.core.cache import cache
from django.conf import settings
from django.template import Context, Template
from django.template.loader import render_to_string
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import translation

from blog.extension_signals import (
    article_deleted,
    article_published,
    article_unpublished,
)
from blog.extensions import (
    get_markdown_extensions,
    register_markdown_extension,
    register_template_hook,
    reset_extension_registry,
)
from blog.models import (
    ArticleModel,
    MenuLink,
    MenuLinkTranslation,
    SiteConfiguration,
)
from blog.templatetags.navbar_utils import menu_label, theme_label


class ExtensionRegistryTests(TestCase):
    def tearDown(self):
        reset_extension_registry()

    def test_template_hooks_render_with_context(self):
        register_template_hook("main_start", "tests/extension-hook.html", priority=20)
        rendered = Template(
            "{% load blog_extensions %}{% render_blog_hook 'main_start' %}"
        ).render(Context({"extension_value": "ready"}))
        self.assertIn("data-extension-hook", rendered)
        self.assertIn("ready", rendered)

    def test_markdown_extensions_can_be_site_aware(self):
        site = object()
        register_markdown_extension(lambda active_site: ("demo", active_site))
        self.assertEqual(get_markdown_extensions(site), [("demo", site)])

    def test_markdown_extension_classes_are_not_called_as_site_factories(self):
        class DemoMarkdownExtension:
            pass

        register_markdown_extension(DemoMarkdownExtension)
        self.assertEqual(get_markdown_extensions(object()), [DemoMarkdownExtension])

    def test_unknown_template_hook_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown template hook"):
            register_template_hook("misspelled_hook", "tests/extension-hook.html")


class ArticleLifecycleSignalTests(TestCase):
    def test_publish_unpublish_and_delete_events_are_distinct(self):
        published = Mock()
        unpublished = Mock()
        deleted = Mock()
        article_published.connect(published, weak=False)
        article_unpublished.connect(unpublished, weak=False)
        article_deleted.connect(deleted, weak=False)
        try:
            article = ArticleModel.objects.create(
                title="Lifecycle", content="Draft", is_published=False
            )
            self.assertFalse(published.called)
            article.is_published = True
            article.save()
            self.assertEqual(published.call_count, 1)
            article.is_published = False
            article.save()
            self.assertEqual(unpublished.call_count, 1)
            article.delete()
            self.assertEqual(deleted.call_count, 1)
        finally:
            article_published.disconnect(published)
            article_unpublished.disconnect(unpublished)
            article_deleted.disconnect(deleted)


class LanguageSwitchTests(TestCase):
    def test_custom_menu_label_uses_admin_translation_and_safe_fallbacks(self):
        site = SiteConfiguration.objects.create(config_name="Menu translations")
        link = MenuLink.objects.create(
            config=site,
            link_location="navbar",
            name="More Info",
            url="/more-info/",
        )
        MenuLinkTranslation.objects.create(
            menu_link=link,
            language_code="zh-hans",
            name="更多信息",
        )

        with translation.override("zh-hans"):
            self.assertEqual(menu_label(link), "更多信息")
        with translation.override("ja"):
            self.assertEqual(menu_label(link), "More Info")
        with translation.override("en"):
            self.assertEqual(menu_label(link), "More Info")

    def test_standard_redefine_menu_labels_are_translated(self):
        expected_about = {
            "en": "About",
            "es": "Acerca de",
            "fr": "À propos",
            "ja": "このブログについて",
            "zh-hans": "关于",
            "zh-hk": "關於",
            "zh-tw": "關於",
        }
        for language_code, expected in expected_about.items():
            with self.subTest(language_code=language_code):
                with translation.override(language_code):
                    self.assertEqual(str(theme_label("About")), expected)

        self.assertEqual(theme_label("A custom page"), "A custom page")

    def test_every_shipped_catalog_covers_the_reader_interface(self):
        locale_root = Path(settings.BASE_DIR) / "locale"

        def catalog_keys(locale_name):
            path = locale_root / locale_name / "LC_MESSAGES" / "django.mo"
            with path.open("rb") as stream:
                catalog = GNUTranslations(stream)._catalog
            return {key for key in catalog if isinstance(key, str) and key}

        source_keys = catalog_keys("zh_Hans")
        extracted_messages = set()
        for path in Path(settings.BASE_DIR).rglob("*.py"):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "_"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                ):
                    extracted_messages.add(node.args[0].value)
        template_pattern = re.compile(
            r'''{%\s*translate\s+(?:"([^"]*)"|'([^']*)')'''
        )
        for path in Path(settings.BASE_DIR).rglob("*.html"):
            for match in template_pattern.finditer(path.read_text(encoding="utf-8")):
                extracted_messages.add(
                    next(value for value in match.groups() if value is not None)
                )
        self.assertLessEqual(extracted_messages, source_keys)

        for locale_name in ("es", "fr", "ja", "zh_Hant", "zh_HK", "zh_TW"):
            with self.subTest(locale_name=locale_name):
                self.assertEqual(catalog_keys(locale_name), source_keys)

    def test_language_menu_matches_upstream_redefine_languages(self):
        self.assertEqual(
            settings.LANGUAGES,
            [
                ("en", "English"),
                ("es", "Español"),
                ("fr", "Français"),
                ("ja", "日本語"),
                ("zh-hans", "简体中文"),
                ("zh-hk", "香港繁體"),
                ("zh-tw", "臺灣正體"),
            ],
        )

        response = self.client.get(reverse("index"))
        for language_code in (
            "en",
            "es",
            "fr",
            "ja",
            "zh-hans",
            "zh-hk",
            "zh-tw",
        ):
            self.assertContains(response, f'value="{language_code}"')
        for flag in ("🇬🇧", "🇪🇸", "🇫🇷", "🇯🇵", "🇨🇳", "🇭🇰", "🇹🇼"):
            self.assertContains(response, flag)

    def test_taiwan_language_flag_is_stable_in_open_source_build(self):
        option_pattern = (
            r'data-language-code="zh-tw".*?'
            r'language-switcher-option-badge[^>]*>(?P<flag>[^<]+)</span>'
        )
        mainland = self.client.get(reverse("index"), HTTP_CF_IPCOUNTRY="CN")
        elsewhere = self.client.get(reverse("index"), HTTP_CF_IPCOUNTRY="US")
        self.assertEqual(
            re.search(option_pattern, mainland.content.decode(), re.S).group("flag"),
            "🇹🇼",
        )
        self.assertEqual(
            re.search(option_pattern, elsewhere.content.decode(), re.S).group("flag"),
            "🇹🇼",
        )

    def test_upstream_theme_copy_is_available_in_added_languages(self):
        expected_read_more = {
            "es": "Leer más",
            "fr": "Lire la suite",
            "ja": "全文を読む",
        }
        for language_code, expected in expected_read_more.items():
            with self.subTest(language_code=language_code):
                with translation.override(language_code):
                    self.assertEqual(translation.gettext("Read more"), expected)

    @override_settings(LANGUAGE_CODE="en")
    def test_language_endpoint_switches_reader_ui(self):
        ArticleModel.objects.all().delete()
        response = self.client.post(
            reverse("set_language"),
            {"language": "zh-hans", "next": reverse("index")},
            follow=True,
        )
        self.assertContains(response, "还没有文章")
        self.assertContains(response, "fa-language")
        self.assertContains(response, "language-switcher-dialog")
        self.assertNotContains(response, 'id="site-language"')

    @override_settings(LANGUAGE_CODE="en")
    def test_mainland_region_defaults_to_simplified_chinese(self):
        response = self.client.get(reverse("index"), HTTP_CF_IPCOUNTRY="CN")
        self.assertEqual(response.headers["Content-Language"], "zh-hans")
        self.assertIn("CF-IPCountry", response.headers["Vary"])
        self.assertRegex(
            response.content.decode(),
            re.compile(
                r'由\s*<a[^>]+href="https://www\.djangoproject\.com/"[^>]*>'
                r'.*?Django\s*</a>\s*强力驱动',
                re.S,
            ),
        )

    @override_settings(LANGUAGE_CODE="en")
    def test_taiwan_and_hong_kong_default_to_traditional_chinese(self):
        for country_code, language_code in (("TW", "zh-tw"), ("HK", "zh-hk")):
            with self.subTest(country_code=country_code, language_code=language_code):
                response = self.client.get(
                    reverse("index"), HTTP_CF_IPCOUNTRY=country_code
                )
                self.assertEqual(response.headers["Content-Language"], language_code)
                self.assertRegex(
                    response.content.decode(),
                    re.compile(
                        r'由\s*<a[^>]+href="https://www\.djangoproject\.com/"[^>]*>'
                        r'.*?Django\s*</a>\s*強力驅動',
                        re.S,
                    ),
                )

        with translation.override("zh-tw"):
            self.assertEqual(translation.gettext("Blog up for"), "部落格已運行")
        with translation.override("zh-hk"):
            self.assertEqual(translation.gettext("Blog up for"), "網誌已運行")

    @override_settings(LANGUAGE_CODE="en")
    def test_manual_language_cookie_overrides_region(self):
        self.client.cookies["django_language"] = "en"
        response = self.client.get(reverse("index"), HTTP_CF_IPCOUNTRY="CN")
        self.assertEqual(response.headers["Content-Language"], "en")
        self.assertRegex(
            response.content.decode(),
            re.compile(
                r'Proudly powered by\s*<a[^>]+href="https://www\.djangoproject\.com/"[^>]*>'
                r'.*?Django\s*</a>',
                re.S,
            ),
        )


class UpstreamEnglishCopyTests(TestCase):
    def tearDown(self):
        cache.clear()

    def test_footer_uses_redefine_english_labels(self):
        site = SiteConfiguration.objects.create(
            config_name="English copy",
            footer_statistics=True,
            footer_runtime_enabled=True,
        )
        with translation.override("en"):
            html = render_to_string(
                "components/footer/footer.html",
                {
                    "site": site,
                    "articles_count": 2,
                    "total_words": 320,
                    "site_uv": 7,
                    "site_pv": 11,
                },
            )

        for text in (
            "2 posts in total",
            "320 words in total",
            "VISITOR COUNT",
            "TOTAL PAGE VIEWS",
            "Proudly powered by",
            "Based on",
            "Blog up for",
            "days",
            "hrs",
            "Min",
            "Sec",
        ):
            self.assertIn(text, html)
        self.assertNotIn(">runtime<", html)

    def test_article_license_matches_redefine_wording(self):
        SiteConfiguration.objects.create(
            config_name="License copy",
            is_active=True,
            copyright_type="cc_by",
        )
        article = ArticleModel.objects.create(title="License", content="Text")
        with translation.override("en"):
            self.assertIn("This work is licensed under", article.licence_label)
            self.assertIn("CC BY 4.0", article.licence_label)
