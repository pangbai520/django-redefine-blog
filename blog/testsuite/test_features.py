from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse

from ..models import (
    ArticleModel,
    AudioTrack,
    Category,
    FriendCategory,
    FriendLink,
    SiteConfiguration,
    Tag,
)

User = get_user_model()


class AudioTrackTests(TestCase):
    def setUp(self):
        self.site = SiteConfiguration.objects.create(
            config_name="Test configuration",
            site_name="Test site",
            is_active=True,
        )

    def test_enabled_player(self):
        AudioTrack.objects.create(
            name="Enabled track",
            artist="Test artist",
            url="/resources/audio/enabled.mp3",
            cover="/resources/covers/enabled.jpg",
        )
        AudioTrack.objects.create(
            name="Disabled track",
            url="/resources/audio/disabled.mp3",
            enabled=False,
        )

        tracks = self.site.aplayer_tracks

        self.assertEqual(len(tracks), 1)
        self.assertEqual(tracks[0]["name"], "Enabled track")
        self.assertEqual(tracks[0]["cover"], "/resources/covers/enabled.jpg")

    def test_player_tracks(self):
        AudioTrack.objects.create(
            name="Rendered track",
            url="/resources/audio/rendered.mp3",
        )

        html = render_to_string("components/plugins/aplayer.html", {"site": self.site})

        self.assertIn('id="aplayer-tracks"', html)
        self.assertIn("Rendered track", html)

    def test_player_json(self):
        self.site.aplayer_type = "mini"
        self.site.aplayer_config = {"mutex": True}

        self.assertTrue(self.site.aplayer_is_mini)
        self.assertEqual(self.site.aplayer_settings["type"], "mini")
        self.assertTrue(self.site.aplayer_settings["mutex"])

    def test_comments_configured(self):
        html = render_to_string("components/comments/comment.html", {"site": self.site})

        self.assertNotIn("comments-container", html)

    def test_selected_container(self):
        self.site.comment_enabled = True
        self.site.comment_system = "giscus"
        self.site.comment_config = {
            "repo": "owner/repo",
            "repo_id": "repo-id",
            "category": "Comments",
            "category_id": "category-id",
        }

        html = render_to_string(
            "components/comments/comment.html",
            {
                "site": self.site,
                "comment_system_configured": True,
            },
        )

        self.assertIn('class="comments-container', html)
        self.assertIn('id="giscus-container"', html)
        self.assertIn('data-repo="owner/repo"', html)

    def test_twikoo_structure(self):
        self.site.comment_enabled = True
        self.site.comment_system = "twikoo"
        self.site.comment_config = {
            "twikoo": {"server_url": "https://comments.example.com"}
        }

        html = render_to_string(
            "components/comments/comment.html",
            {
                "site": self.site,
                "comment_system_configured": True,
            },
        )

        self.assertIn('class="twikoo-container"', html)
        self.assertIn('id="twikoo-comment"', html)

    def test_original_supported(self):
        self.site.comment_enabled = True
        self.site.comment_system = "waline"
        self.site.comment_config = {
            "waline": {
                "serverUrl": "https://comments.example.com",
                "lang": "zh-CN",
            }
        }

        html = render_to_string(
            "components/comments/comment.html",
            {
                "site": self.site,
                "comment_system_configured": True,
            },
        )

        self.assertIn("https://comments.example.com", html)
        self.assertIn('"lang": "zh-CN"', html)

    def test_waline_options(self):
        self.site.comment_enabled = True
        self.site.comment_system = "waline"
        self.site.comment_config = {
            "waline": {
                "serverUrl": "https://comments.example.com",
                "lang": "en-US",
                "emoji": ["https://cdn.example.com/emoji"],
                "reaction": ["https://cdn.example.com/reaction.webp"],
                "turnstileKey": "turnstile-key",
            }
        }

        html = render_to_string(
            "components/comments/comment.html",
            {"site": self.site, "comment_system_configured": True},
        )

        self.assertIn('"emoji": ["https://cdn.example.com/emoji"]', html)
        self.assertIn('"reaction": ["https://cdn.example.com/reaction.webp"]', html)
        self.assertIn('"turnstileKey": "turnstile-key"', html)

    def test_friends_layout(self):
        category = FriendCategory.objects.create(name="Blogs")
        FriendLink.objects.create(
            category=category,
            name="Example blog",
            link="https://example.com/",
            description="A friend site",
        )

        response = self.client.get(reverse("friends"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "friends-link-container")
        self.assertContains(response, "Example blog")


class TagPageTests(TestCase):
    def test_article_brackets(self):
        article = ArticleModel.objects.create(
            title="TOC article",
            slug="toc-article",
            content="# Parent\n\n## Child",
            is_published=True,
        )

        self.assertIn('<ol class="nav">', article.toc)
        self.assertIn('<ol class="nav-child">', article.toc)
        self.assertIn('<span class="nav-text">Parent</span>', article.toc)
        self.assertNotIn("<ul", article.toc)
        self.assertNotIn('<div class="toc">', article.toc)
        self.assertNotIn('<ol class="nav">>', article.toc)
        self.assertNotIn('<ol class="nav-child">>', article.toc)

    def test_search_shape(self):
        article = ArticleModel.objects.create(
            title="Searchable article",
            slug="searchable-article",
            content="A searchable body",
            is_published=True,
        )
        response = self.client.get(reverse("search_data"), {"q": "searchable"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["results"][0]["title"], article.title)
        self.assertIn("content", payload["results"][0])
        self.assertTrue(
            payload["results"][0]["url"].endswith(article.get_absolute_url())
        )
        self.assertIn(
            payload["backend"],
            {
                "sqlite-fts5",
                "mysql-fulltext",
                "postgresql-search-vector",
                "database-fallback",
            },
        )

    def test_categories_list(self):
        parent = Category.objects.create(name="Development", slug="development")
        child = Category.objects.create(name="Django", slug="django", parent=parent)
        article = ArticleModel.objects.create(
            title="Nested category article",
            slug="nested-category-article",
            content="body",
            is_published=True,
        )
        article.category.add(child)
        response = self.client.get(reverse("categories"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "all-category-list-child")
        self.assertContains(response, "Django")

    def test_tag_title(self):
        tag = Tag.objects.create(name="Python", slug="python")
        article = ArticleModel.objects.create(
            title="Tagged article",
            slug="tagged-article",
            content="Article content",
            is_published=True,
        )
        article.tags.add(tag)

        response = self.client.get(reverse("tags_detail", args=[tag.slug]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="tag-name"')
        self.assertNotContains(response, "<h1>Tags</h1>")

    def test_article_enabled(self):
        site = SiteConfiguration.objects.create(
            config_name="Recommendations",
            site_name="Test site",
            is_active=True,
            recommendation_enabled=True,
            recommendation_limit=3,
            recommendation_mobile_limit=1,
        )
        tag = Tag.objects.create(name="Django", slug="django")
        article = ArticleModel.objects.create(
            title="Current article",
            slug="current-article",
            content="Django templates",
            is_published=True,
        )
        related = ArticleModel.objects.create(
            title="Related article",
            slug="related-article",
            content="Django templates and views",
            is_published=True,
        )
        article.tags.add(tag)
        related.tags.add(tag)

        response = self.client.get(reverse("article", args=[article.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "recommended-article")
        self.assertContains(response, "recommended-desktop")
        self.assertContains(response, related.get_absolute_url())
