from datetime import datetime, timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from ..templatetags.author_label_utils import get_author_label

from ..models import (
    ArticleModel,
    Category,
    MenuLink,
    SiteConfiguration,
    StandalonePage,
    Tag,
)

User = get_user_model()


class ArchivePageTests(TestCase):
    def test_archive_ordering(self):
        now = timezone.now()
        for index in range(11):
            ArticleModel.objects.create(
                title=f"Archive article {index}",
                slug=f"archive-article-{index}",
                content="Archive content",
                is_published=True,
                sticky=1 if index == 10 else 0,
                created_at=now - timedelta(days=index),
            )

        response = self.client.get(reverse("archives"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Archive article 10")
        self.assertContains(response, "Archive article 0")


class AuthorLabelTests(TestCase):
    def test_json_supported(self):
        self.assertEqual(get_author_label(8, False, ["New", "Regular"]), "Regular")


class RedefineParityTests(TestCase):
    def setUp(self):
        cache.clear()
        self.site = SiteConfiguration.objects.create(
            config_name="Parity",
            site_name="Parity site",
            is_active=True,
        )

    def test_home_metadata(self):
        article = ArticleModel.objects.create(
            title="Metadata",
            content="Body",
            is_published=True,
        )
        category = Category.objects.create(name="News", slug="news")
        tag = Tag.objects.create(name="Django", slug="django")
        article.category.add(category)
        article.tags.add(tag)
        self.site.article_categories_enabled = False
        self.site.article_tags_enabled = False
        self.site.save()
        cache.clear()

        self.assertEqual(article._categories_meta(self.site, limited=True), [])
        self.assertEqual(article._tags_meta(self.site, limited=True), [])
        self.assertEqual(
            article._categories_meta(self.site, limited=False)[0]["name"], "News"
        )
        self.assertEqual(
            article._tags_meta(self.site, limited=False)[0]["name"], "Django"
        )

    def test_zero_unlimited(self):
        self.site.article_categories_limit = 0
        self.site.article_tags_limit = 0
        self.site.full_clean()

    def test_auto_posts(self):
        self.site.article_dateformat = "auto"
        self.site.save()
        cache.clear()
        article = ArticleModel.objects.create(
            title="Old",
            content="Body",
            is_published=True,
            created_at=timezone.now() - timedelta(days=30),
        )

        self.assertRegex(article.meta["home_date"], r"^\d{4}-\d{2}-\d{2}$")

    def test_custom_supported(self):
        self.site.article_dateformat = "YYYY/M/D [at] H:mm"
        self.site.save()
        cache.clear()
        article = ArticleModel.objects.create(
            title="Custom date",
            content="Body",
            is_published=True,
            created_at=timezone.make_aware(datetime(2026, 10, 5, 9, 7, 0)),
        )

        self.assertEqual(article.meta["home_date"], "2026/10/5 at 9:07")

    def test_second_page(self):
        for index in range(11):
            ArticleModel.objects.create(
                title=f"Post {index}",
                slug=f"post-{index}",
                content="Body",
                is_published=True,
                created_at=timezone.now() - timedelta(days=index),
            )

        response = self.client.get(reverse("index"), {"page": 2})

        self.assertContains(response, 'data-home-first-page="false"')
        self.assertNotContains(
            response, 'class="navbar-content transition-navbar has-home-banner"'
        )

    def test_social_button(self):
        self.site.social_links_enabled = True
        self.site.social_links_style = "center"
        html = render_to_string("pages/home/home-banner.html", {"site": self.site})

        self.assertIn('class="hidden p-3', html)

    def test_social_destination(self):
        self.site.social_links_enabled = True
        MenuLink.objects.create(
            config=self.site,
            link_location="social",
            name="https://cdn.example.com/icon.svg",
            url="https://example.com/profile",
        )

        html = render_to_string("pages/home/home-banner.html", {"site": self.site})

        self.assertIn('href="https://example.com/profile"', html)
        self.assertIn('src="https://cdn.example.com/icon.svg"', html)

    def test_mobile_links(self):
        MenuLink.objects.create(
            config=self.site,
            link_location="navbar",
            name="Archives",
            url="/archives/",
        )
        MenuLink.objects.create(
            config=self.site,
            link_location="sidebar",
            name="Archives",
            url="/archives/",
        )

        self.assertEqual(self.site.mobile_sidebar_links, [])

    def test_footer_independent(self):
        self.site.footer_statistics = False
        self.site.website_counter_enabled = True
        html = render_to_string(
            "components/footer/footer.html",
            {
                "site": self.site,
                "articles_count": 2,
                "total_words": 10,
                "site_uv": 3,
                "site_pv": 4,
            },
        )

        self.assertNotIn("2 posts in total", html)
        self.assertIn("VISITOR COUNT", html)

    def test_article_image(self):
        self.site.og_description = ""
        self.site.save(update_fields=["og_description"])
        article = ArticleModel.objects.create(
            title="Article title",
            excerpt="Article description",
            content="Body",
            is_published=True,
        )
        tag = Tag.objects.create(name="Django", slug="django")
        article.tags.add(tag)
        request = RequestFactory().get("/article/article-title/")
        request.resolver_match = type("Match", (), {"url_name": "article"})()
        html = render_to_string(
            "components/header/head.html",
            {
                "site": self.site,
                "article": article,
                "page_title": article.title,
                "request": request,
                "SITE_LANG": "en",
            },
        )

        self.assertIn('property="og:title" content="Article title"', html)
        self.assertIn('property="og:description" content="Article description"', html)
        self.assertIn('property="article:tag" content="Django"', html)
        self.assertIn('property="og:image" content="http://testserver/static/', html)

    def test_home_priority(self):
        article = ArticleModel(
            thumbnail=SimpleUploadedFile("thumbnail.png", b"thumbnail"),
            cover=SimpleUploadedFile("cover.png", b"cover"),
            banner=SimpleUploadedFile("banner.png", b"banner"),
        )

        self.assertTrue(article.thumbnail_url.endswith("thumbnail.png"))
        self.assertTrue(article.article_cover_url.endswith("cover.png"))

    def test_article_format(self):
        midnight = timezone.make_aware(datetime(1900, 1, 1, 0, 0, 0))
        whole_minute = timezone.make_aware(datetime(2026, 10, 25, 14, 6, 0))
        article = ArticleModel(created_at=midnight)
        article.updated_at = whole_minute

        self.assertEqual(article.created_at_display, "1900-01-01")
        self.assertEqual(article.updated_at_display, "2026-10-25 14:06")
        self.assertTrue(article.has_meaningful_update)

    def test_immediate_repeated(self):
        created = timezone.now()
        article = ArticleModel(created_at=created)
        article.updated_at = created + timedelta(milliseconds=500)

        self.assertFalse(article.has_meaningful_update)

    def test_long_gaps(self):
        for index in range(121):
            ArticleModel.objects.create(
                title=f"Long archive {index}",
                slug=f"long-archive-{index}",
                content="Body",
                is_published=True,
                created_at=timezone.now() - timedelta(days=index),
            )

        response = self.client.get(reverse("index"), {"page": 7})

        self.assertContains(response, '<span class="space">&hellip;</span>', count=2)
        self.assertNotContains(response, 'href="?page=2">2</a>')

    def test_cloud_limit(self):
        page = StandalonePage.objects.get(
            config=self.site, page_type=StandalonePage.TAGS
        )
        page.tags_style = "cloud"
        page.save(update_fields=["tags_style", "updated_at"])
        article = ArticleModel.objects.create(
            title="Many tags",
            content="Body",
            is_published=True,
        )
        tags = [Tag(name=f"Tag {index}", slug=f"tag-{index}") for index in range(101)]
        Tag.objects.bulk_create(tags)
        article.tags.add(*Tag.objects.all())
        cache.clear()

        response = self.client.get(reverse("tags"))

        self.assertEqual(len(response.context["tags"]), 100)
        self.assertContains(response, "Tag 0")

    def test_mobile_desktop(self):
        MenuLink.objects.create(
            config=self.site,
            link_location="navbar",
            name="Home",
            url="/",
        )

        response = self.client.get(reverse("index"), HTTP_ACCEPT_LANGUAGE="zh-CN")

        self.assertGreaterEqual(response.content.decode().count("首页"), 2)

    def test_empty_title(self):
        self.site.preloader_message = ""

        html = render_to_string(
            "components/header/preloader.html",
            {"site": self.site},
        )

        self.assertIn("Parity site", html)

    def test_emergency_defaults(self):
        SiteConfiguration.objects.all().delete()
        cache.clear()

        site = SiteConfiguration.load()

        self.assertEqual(site.site_name, "Django Redefine")
        self.assertEqual(site.preloader_message, "")

    def test_bookmark_scope(self):
        StandalonePage.objects.filter(
            config=self.site, page_type=StandalonePage.BOOKMARKS
        ).update(enabled=True)
        cache.clear()

        response = self.client.get(reverse("bookmarks"))

        self.assertContains(response, 'class="bookmarks-page py-8 sm:py-0"')

    def test_bookmark_category(self):
        script = (
            Path(__file__).parent.parent
            / "static"
            / "js"
            / "layouts"
            / "bookmarkNav.js"
        ).read_text(encoding="utf-8")
        main_script = (
            Path(__file__).parent.parent / "static" / "js" / "main.js"
        ).read_text(encoding="utf-8")
        stylesheet = (
            Path(__file__).parent.parent / "static" / "css" / "style.css"
        ).read_text(encoding="utf-8")

        self.assertIn('item.classList.remove("bg-second-background-color")', script)
        self.assertIn('item.classList.add("bg-second-background-color")', script)
        self.assertNotIn('item.classList.toggle(\n                "active"', script)
        self.assertNotIn('item.addEventListener(\n            "click"', script)
        self.assertIn(
            'import initBookmarkNav from "./layouts/bookmarkNav.js";', main_script
        )
        self.assertIn("initBookmarkNav();", main_script)
        self.assertIn(".bookmark-nav-item.active {", stylesheet)
        self.assertIn("background-color: var(--second-background-color);", stylesheet)
        self.assertNotIn(".bookmarks-page .bookmark-card-link:hover", stylesheet)

    def test_profile_errors(self):
        stylesheet = (
            Path(__file__).parent.parent / "static" / "css" / "profile.css"
        ).read_text(encoding="utf-8")

        self.assertIn(
            ".profile-help ul { margin: 4px 0 0; padding-left: 1.25rem; }", stylesheet
        )
        self.assertIn(".profile-field-errors .errorlist", stylesheet)
        self.assertIn("list-style: none !important", stylesheet)

    def test_delete_animation(self):
        stylesheet = (
            Path(__file__).parent.parent / "static" / "css" / "profile.css"
        ).read_text(encoding="utf-8")

        self.assertIn(
            ".profile-delete-link:hover { border-color: #b42318; color: #fff; background: #b42318; }",
            stylesheet,
        )

    def test_info_spacing(self):
        self.site.sidebar_firstitem = "info"
        self.site.sidebar_announcement = "<strong>Notice</strong>"
        self.site.save(update_fields=["sidebar_firstitem", "sidebar_announcement"])
        cache.clear()

        html = render_to_string(
            "pages/home/home-sidebar.html",
            {
                "site": self.site,
                "post_count": 0,
                "articles_count": 0,
                "tags_count": 0,
                "categories_count": 0,
            },
        )

        self.assertIn('class="sidebar-links" marginTop', html)
        self.assertIn("<strong>Notice</strong>", html)

    def test_manual_markdown(self):
        article = ArticleModel.objects.create(
            title="Excerpt",
            excerpt="A **formatted** [link](https://example.com).",
            content="Body",
            is_published=True,
        )

        rendered = str(article.auto_excerpt)

        self.assertIn("<strong>formatted</strong>", rendered)
        self.assertIn('href="https://example.com"', rendered)
