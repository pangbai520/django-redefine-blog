import base64
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from django.template.loader import render_to_string
from django.conf import settings
from django.test import RequestFactory, TestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.cache import cache
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.forms.models import model_to_dict
from django.urls import reverse
from unittest.mock import patch
from django.utils import timezone

from .templatetags.author_label_utils import get_author_label

from .models import (
    ArticleModel,
    Category,
    AudioTrack,
    FriendCategory,
    FriendLink,
    SiteConfiguration,
    StandalonePage,
    Tag,
    Comment,
    CommentBadge,
    CommentBadgeAssignment,
    CommentBadgeTranslation,
    CommentEmoji,
    CommentEmojiPack,
    CommentGifSource,
    CommentImage,
    MenuLink,
    TrafficModel,
)
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from markdown import Markdown

from core.markdown.extensions import get_extensions
from .admin import ArticleAdmin, FriendCategoryAdmin, SiteConfigurationAdmin, SiteConfigurationForm
from .context_processors import site_processor


User = get_user_model()


class AudioTrackTests(TestCase):
    def setUp(self):
        self.site = SiteConfiguration.objects.create(
            config_name="Test configuration",
            site_name="Test site",
            is_active=True,
        )

    def test_enabled_tracks_are_exposed_to_the_player(self):
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

    def test_player_template_contains_database_tracks(self):
        AudioTrack.objects.create(
            name="Rendered track",
            url="/resources/audio/rendered.mp3",
        )

        html = render_to_string("components/plugins/aplayer.html", {"site": self.site})

        self.assertIn('id="aplayer-tracks"', html)
        self.assertIn("Rendered track", html)

    def test_player_mode_is_selected_outside_advanced_json(self):
        self.site.aplayer_type = "mini"
        self.site.aplayer_config = {"mutex": True}

        self.assertTrue(self.site.aplayer_is_mini)
        self.assertEqual(self.site.aplayer_settings["type"], "mini")
        self.assertTrue(self.site.aplayer_settings["mutex"])

    def test_comments_are_hidden_when_the_provider_is_not_configured(self):
        html = render_to_string("components/comments/comment.html", {"site": self.site})

        self.assertNotIn("comments-container", html)

    def test_selected_comment_provider_renders_its_container(self):
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

    def test_twikoo_comment_keeps_redefine_container_structure(self):
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

    def test_original_redefine_nested_comment_config_is_supported(self):
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

    def test_waline_preserves_redefine_provider_options(self):
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

    def test_friends_page_uses_the_hexo_link_layout(self):
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
    def test_article_toc_lists_do_not_emit_stray_angle_brackets(self):
        article = ArticleModel.objects.create(
            title="TOC article",
            slug="toc-article",
            content="# Parent\n\n## Child",
            is_published=True,
        )

        self.assertIn('<ol class="nav">', article.toc)
        self.assertIn('<ol class="nav-child">', article.toc)
        self.assertIn('<span class="nav-text">Parent</span>', article.toc)
        self.assertNotIn('<ul', article.toc)
        self.assertNotIn('<div class="toc">', article.toc)
        self.assertNotIn('<ol class="nav">>', article.toc)
        self.assertNotIn('<ol class="nav-child">>', article.toc)

    def test_search_data_matches_redefine_json_shape(self):
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
        self.assertTrue(payload["results"][0]["url"].endswith(article.get_absolute_url()))
        self.assertIn(
            payload["backend"],
            {
                "sqlite-fts5",
                "mysql-fulltext",
                "postgresql-search-vector",
                "database-fallback",
            },
        )

    def test_categories_render_nested_redefine_list(self):
        parent = Category.objects.create(name="Development", slug="development")
        child = Category.objects.create(name="Django", slug="django", parent=parent)
        article = ArticleModel.objects.create(
            title="Nested category article", slug="nested-category-article", content="body", is_published=True
        )
        article.category.add(child)
        response = self.client.get(reverse("categories"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "all-category-list-child")
        self.assertContains(response, "Django")

    def test_tag_detail_does_not_render_a_second_page_title(self):
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

    def test_article_recommendations_follow_redefine_layout_when_enabled(self):
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
            title="Current article", slug="current-article", content="Django templates", is_published=True
        )
        related = ArticleModel.objects.create(
            title="Related article", slug="related-article", content="Django templates and views", is_published=True
        )
        article.tags.add(tag)
        related.tags.add(tag)

        response = self.client.get(reverse("article", args=[article.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "recommended-article")
        self.assertContains(response, "recommended-desktop")
        self.assertContains(response, related.get_absolute_url())


class CorePublishingTests(TestCase):
    def test_future_dated_articles_are_not_public_until_their_publish_time(self):
        baseline_words = self.client.get(reverse("index")).context["total_words"]
        category = Category.objects.create(name="Scheduled category", slug="scheduled-category")
        tag = Tag.objects.create(name="Scheduled tag", slug="scheduled-tag")
        article = ArticleModel.objects.create(
            title="Scheduled article",
            content="Not public yet",
            is_published=True,
            created_at=timezone.now() + timedelta(days=1),
        )
        article.category.add(category)
        article.tags.add(tag)

        self.assertFalse(ArticleModel.objects.published().filter(pk=article.pk).exists())
        self.assertEqual(self.client.get(article.get_absolute_url()).status_code, 404)
        index_response = self.client.get(reverse("index"))
        self.assertNotContains(index_response, article.title)
        self.assertEqual(index_response.context["total_words"], baseline_words)
        self.assertNotContains(
            self.client.get(reverse("search_data"), {"q": "Scheduled"}),
            article.title,
        )
        self.assertNotContains(self.client.get(reverse("categories")), category.name)
        self.assertNotContains(self.client.get(reverse("tags")), tag.name)

    def test_editing_an_article_title_keeps_its_public_slug(self):
        article = ArticleModel.objects.create(
            title="Original title",
            content="Body",
            is_published=True,
        )
        original_slug = article.slug

        article.title = "Renamed title"
        article.save()
        article.refresh_from_db()

        self.assertEqual(article.slug, original_slug)

    def test_content_only_update_persists_derived_counters(self):
        article = ArticleModel.objects.create(title="Counters", content="one")
        original_count = article.word_counter

        article.content = "one two three four"
        article.save(update_fields=("content",))
        article.refresh_from_db()

        self.assertGreater(article.word_counter, original_count)
        self.assertGreaterEqual(article.reading_time, 1)

    def test_category_parent_cycle_is_rejected(self):
        parent = Category.objects.create(name="Parent", slug="parent")
        child = Category.objects.create(name="Child", slug="child", parent=parent)
        parent.parent = child

        with self.assertRaises(ValidationError):
            parent.full_clean()

    def test_article_and_traffic_changes_invalidate_stat_caches(self):
        cache.set("total_word_count", 1)
        cache.set("site_stats_counts", {"articles_count": 1})
        article = ArticleModel.objects.create(
            title="Cache invalidation",
            content="Body",
            is_published=True,
        )

        self.assertIsNone(cache.get("total_word_count"))
        self.assertIsNone(cache.get("site_stats_counts"))

        cache.set("site_stats_counts", {"tags_count": 0})
        tag = Tag.objects.create(name="Cache", slug="cache")
        article.tags.add(tag)
        self.assertIsNone(cache.get("site_stats_counts"))

        cache.set("site_traffic", {"site_pv": 1})
        TrafficModel.objects.create(path="/", ip="192.0.2.20", user_agent="Browser")
        self.assertIsNone(cache.get("site_traffic"))


class InternalCommentTests(TestCase):
    def setUp(self):
        cache.clear()
        self.site = SiteConfiguration.objects.create(
            config_name="Internal comments",
            site_name="Test site",
            is_active=True,
            comment_enabled=True,
            comment_system="internal",
        )
        self.article = ArticleModel.objects.create(
            title="Comment article",
            slug="comment-article",
            content="Article content",
            is_published=True,
        )

    def test_guest_comment_is_created(self):
        response = self.client.post(
            reverse("comment_create", args=[self.article.slug]),
            {"nickname": "Guest", "content": "Hello"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Comment.objects.count(), 1)
        self.assertEqual(response.json()["comment"]["author"], "Guest")

    def test_login_required_composer_keeps_editor_and_offers_sign_in_and_sign_up(self):
        self.site.comment_require_login = True
        self.site.comment_registration_enabled = True
        self.site.save(
            update_fields=["comment_require_login", "comment_registration_enabled"]
        )

        response = self.client.get(reverse("article", args=[self.article.slug]))

        self.assertContains(response, "internal-comment-panel is-locked")
        self.assertContains(response, "fa-solid fa-lock")
        self.assertContains(response, 'class="wl-editor"')
        self.assertContains(response, "disabled")
        self.assertContains(response, 'data-auth-open-panel="login"')
        self.assertContains(response, 'data-auth-open-panel="register"')
        self.assertContains(response, "data-no-swup", count=2)
        self.assertContains(response, "Sign in")
        self.assertContains(response, "Sign up")
        self.assertNotContains(response, "modal=1")
        self.assertContains(response, "js/comments/internal.js")
        self.assertNotContains(response, "internal.js?")
        self.assertContains(response, 'data-msg-comment-length=')
        self.assertContains(response, 'data-authenticated="false"')
        self.assertContains(response, 'data-comment-require-login="true"')
        self.assertContains(response, 'data-comment-toasts')
        self.assertContains(response, 'data-comment-confirm')
        self.assertContains(response, 'class="internal-auth-heading-icon"')
        self.assertContains(response, "fa-solid fa-right-to-bracket")
        self.assertContains(response, "fa-solid fa-user-plus")
        self.assertContains(response, "fa-solid fa-envelope")
        self.assertContains(response, "fa-solid fa-shield-halved")
        self.assertNotContains(response, 'class="internal-auth-field"><i class=')

        source = (
            Path(__file__).parent / "static" / "js" / "comments" / "internal.js"
        ).read_text(encoding="utf-8")
        self.assertIn('root.addEventListener("click"', source)
        self.assertIn('event.target.closest(".internal-auth-open")', source)
        self.assertIn("}, true);", source)
        self.assertIn("setTimeout(function () { openAuthModal(requestedPanel); }, 0)", source)
        self.assertIn('root.dataset.authHandlerVersion = "delegated-v3"', source)

    def test_fenced_comment_code_uses_the_configured_highlight_palette(self):
        source = '```python\nprint("hello world")\n```'
        response = self.client.post(
            reverse("comment_create", args=[self.article.slug]),
            {"nickname": "Guest", "content": source},
        )

        self.assertEqual(response.status_code, 200)
        html = response.json()["comment"]["content_html"]
        self.assertIn('<pre><code class="hljs language-python">', html)
        self.assertIn('class="hljs-variable"', html)
        self.assertIn('class="hljs-string"', html)
        self.assertNotIn("```", html)

    def test_comment_preview_matches_the_posted_markdown_pipeline(self):
        source = 'Text\n\n```python\nprint("hello world")\n```'
        preview = self.client.post(reverse("comment_preview"), {"content": source})
        posted = self.client.post(
            reverse("comment_create", args=[self.article.slug]),
            {"nickname": "Guest", "content": source},
        )

        self.assertEqual(preview.status_code, 200)
        self.assertEqual(posted.status_code, 200)
        self.assertEqual(
            preview.json()["html"],
            posted.json()["comment"]["content_html"],
        )

    def test_comment_preview_resolves_configured_emoji(self):
        pack = CommentEmojiPack.objects.create(config=self.site, name="Bilibili")
        CommentEmoji.objects.create(
            pack=pack,
            name="bmoji_doge",
            image_url="https://example.com/doge.png",
        )

        preview = self.client.post(
            reverse("comment_preview"),
            {"content": ":bmoji_doge:"},
        )

        self.assertEqual(preview.status_code, 200)
        self.assertIn("internal-comment-emoji", preview.json()["html"])
        self.assertIn("https://example.com/doge.png", preview.json()["html"])

    def test_username_immutability_hint_only_appears_on_registration_panel(self):
        response = self.client.get(reverse("article", args=[self.article.slug]))
        html = response.content.decode()
        login_panel, register_panel = html.split('data-auth-panel="register"', 1)

        self.assertNotIn("Your username cannot be changed after registration.", login_panel)
        self.assertIn("Your username cannot be changed after registration.", register_panel)

    def test_badge_name_uses_the_current_language_translation(self):
        user = User.objects.create_user("translated-badge", password="A-strong-password-123")
        badge = CommentBadge.objects.create(config=self.site, name="Owner", enabled=True)
        CommentBadgeTranslation.objects.update_or_create(
            badge=badge, language_code="zh-hans", defaults={"name": "博主"}
        )
        CommentBadgeAssignment.objects.create(user=user, badge=badge)
        Comment.objects.create(article=self.article, author=user, content="Hello")
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "zh-hans"

        payload = self.client.get(reverse("comment_list", args=[self.article.slug])).json()

        self.assertEqual(payload["comments"][0]["badges"][0]["name"], "博主")

    def test_identical_comment_uploads_reuse_one_storage_object(self):
        user = User.objects.create_user("dedupe-uploader", password="A-strong-password-123")
        self.client.force_login(user)
        png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQABpfZFQAAAAABJRU5ErkJggg==")

        with tempfile.TemporaryDirectory(dir=settings.BASE_DIR) as media_root, override_settings(MEDIA_ROOT=media_root):
            first = self.client.post(
                reverse("comment_upload"),
                {"image": SimpleUploadedFile("first.png", png, content_type="image/png")},
            )
            second = self.client.post(
                reverse("comment_upload"),
                {"image": SimpleUploadedFile("second.png", png, content_type="image/png")},
            )

            self.assertEqual(first.json()["url"], second.json()["url"])
            self.assertEqual(first.json()["image_id"], second.json()["image_id"])
            self.assertEqual(CommentImage.objects.count(), 1)
            self.assertEqual(len(list(Path(media_root, "comment-images").glob("*.png"))), 1)

    def test_uploaded_image_ids_follow_two_comments_and_delete_only_after_last_reference(self):
        user = User.objects.create_user("image-lifecycle", password="A-strong-password-123")
        self.client.force_login(user)
        png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQABpfZFQAAAAABJRU5ErkJggg==")

        with tempfile.TemporaryDirectory(dir=settings.BASE_DIR) as media_root, override_settings(MEDIA_ROOT=media_root):
            first_upload = self.client.post(
                reverse("comment_upload"),
                {"image": SimpleUploadedFile("one.png", png, content_type="image/png")},
            ).json()
            first_response = self.client.post(
                reverse("comment_create", args=[self.article.slug]),
                {"content": f"![image]({first_upload['url']})", "image_ids": first_upload["image_id"]},
            )
            second_upload = self.client.post(
                reverse("comment_upload"),
                {"image": SimpleUploadedFile("two.png", png, content_type="image/png")},
            ).json()
            second_response = self.client.post(
                reverse("comment_create", args=[self.article.slug]),
                {"content": f"![image]({second_upload['url']})", "image_ids": second_upload["image_id"]},
            )
            first_comment = Comment.objects.get(pk=first_response.json()["comment"]["id"])
            second_comment = Comment.objects.get(pk=second_response.json()["comment"]["id"])
            stored_path = Path(media_root, CommentImage.objects.first().image.name)

            self.assertEqual(first_upload["url"], second_upload["url"])
            self.assertEqual(CommentImage.objects.count(), 2)
            self.assertTrue(stored_path.exists())
            with self.captureOnCommitCallbacks(execute=True):
                first_comment.delete()
            self.assertTrue(stored_path.exists())
            with self.captureOnCommitCallbacks(execute=True):
                second_comment.delete()
            self.assertFalse(stored_path.exists())
            self.assertFalse(CommentImage.objects.exists())

    def test_shared_comment_image_is_deleted_only_after_its_last_comment(self):
        user = User.objects.create_user(
            "shared-image-owner", password="A-strong-password-123"
        )
        first_comment = Comment.objects.create(
            article=self.article, author=user, content="First reference"
        )
        second_comment = Comment.objects.create(
            article=self.article, author=user, content="Second reference"
        )

        with tempfile.TemporaryDirectory(dir=settings.BASE_DIR) as media_root, override_settings(MEDIA_ROOT=media_root):
            relative_path = "comment-images/shared.png"
            stored_path = Path(media_root, relative_path)
            stored_path.parent.mkdir(parents=True, exist_ok=True)
            stored_path.write_bytes(b"shared image bytes")
            CommentImage.objects.create(
                uploader=user, comment=first_comment, image=relative_path
            )
            CommentImage.objects.create(
                uploader=user, comment=second_comment, image=relative_path
            )

            with self.captureOnCommitCallbacks(execute=True):
                first_comment.delete()
            self.assertTrue(stored_path.exists())
            self.assertEqual(
                CommentImage.objects.filter(image=relative_path).count(), 1
            )

            with self.captureOnCommitCallbacks(execute=True):
                second_comment.delete()
            self.assertFalse(stored_path.exists())
            self.assertFalse(CommentImage.objects.filter(image=relative_path).exists())

    @patch("blog.comment_views.default_storage.url", return_value="/media/comment-images/test.png")
    @patch("blog.comment_views.default_storage.save", return_value="comment-images/test.png")
    def test_comment_upload_route_is_not_captured_as_a_slug(self, _save, _url):
        user = User.objects.create_user("uploader", password="A-strong-password-123")
        self.client.force_login(user)
        # use a real one-pixel PNG, so byte validation is exercised instead of mocked
        png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQABpfZFQAAAAABJRU5ErkJggg==")
        # isolate storage I/O while retaining the real routing, authentication,
        # MIME checks and image-byte validation exercised by this request
        response = self.client.post(
            reverse("comment_upload"),
            {"image": SimpleUploadedFile("test.png", png, content_type="image/png")},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["url"])
        upload = CommentImage.objects.get()
        self.assertEqual(upload.uploader, user)
        self.assertIsNone(upload.comment_id)

    @patch("blog.comment_views.default_storage.url", return_value="/media/comment-images/test.png")
    @patch("blog.comment_views.default_storage.save", return_value="comment-images/test.png")
    def test_comment_upload_is_attached_and_removed_with_edited_content(self, _save, _url):
        user = User.objects.create_user("image-owner", password="A-strong-password-123")
        self.client.force_login(user)
        png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQABpfZFQAAAAABJRU5ErkJggg==")
        upload_response = self.client.post(
            reverse("comment_upload"),
            {"image": SimpleUploadedFile("test.png", png, content_type="image/png")},
        )
        image_url = upload_response.json()["url"]
        create_response = self.client.post(
            reverse("comment_create", args=[self.article.slug]),
            {"content": f"Attached image\n\n![image]({image_url})"},
        )
        comment = Comment.objects.get(pk=create_response.json()["comment"]["id"])
        upload = CommentImage.objects.get()
        self.assertEqual(upload.comment, comment)

        edit_response = self.client.post(
            reverse("comment_edit", args=[comment.pk]),
            {"content": "Image removed"},
        )
        self.assertEqual(edit_response.status_code, 200)
        self.assertFalse(CommentImage.objects.exists())

    def test_comment_upload_rejects_invalid_image_bytes(self):
        user = User.objects.create_user("invalid-uploader", password="A-strong-password-123")
        self.client.force_login(user)
        response = self.client.post(
            reverse("comment_upload"),
            {"image": SimpleUploadedFile("test.png", b"not an image", content_type="image/png")},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])

    def test_comment_frontend_script_syntax_and_interaction_guards(self):
        script = Path(__file__).parent / "static" / "js" / "comments" / "internal.js"
        source = script.read_text(encoding="utf-8")
        # cover the interaction paths that previously regressed, so emoji/GIF
        # insertion, popup closing and like locking cannot silently break again
        for marker in (
            'insertAtCursor(node.querySelector(".wl-editor"), token)',
            'insertAtCursor(node.querySelector(".wl-editor"), gifMarkdown)',
            'if (!action && !event.target.closest(".internal-comment-picker"))',
            'if (sequence !== gifSearchSequence) return;',
            'if (likeButton && !likeButton.disabled)',
            'if (!isAuthenticated && commentRequiresLogin)',
            'if (!isAuthenticated)',
            'openAuthModal("login")',
            'showToast(error.message, "error")',
            'if (!content || content.length > 5000)',
            'node.dataset.submitting === "true"',
            'requestConfirmation(message("DeleteConfirm", "Delete this comment?"))',
            'replyNeedsAuth ? " internal-auth-open"',
            '!isAuthenticated ? " internal-auth-open"',
            'extractFencedCodeBlocks(value)',
            'fetch("/api/comments/preview/"',
        ):
            self.assertIn(marker, source)
        self.assertNotIn("alert(", source)
        self.assertNotIn("confirm(", source)

    @patch("blog.comment_views._rate_limited")
    def test_empty_comment_is_rejected_before_rate_limiting(self, rate_limited):
        response = self.client.post(
            reverse("comment_create", args=[self.article.slug]),
            {"nickname": "Guest", "content": "   \n\t"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"],
            "Comment length must be between 1 and 5000 characters.",
        )
        rate_limited.assert_not_called()

    def test_comment_code_blocks_reuse_the_article_highlight_palette(self):
        stylesheet = Path(__file__).parent / "static" / "css" / "internal-comments.css"
        source = stylesheet.read_text(encoding="utf-8")
        palette = (
            Path(__file__).parent / "static" / "css" / "codeblock-settings.css"
        ).read_text(encoding="utf-8")

        self.assertIn("background: var(--highlight-background);", source)
        self.assertIn("color: var(--highlight-foreground);", source)
        self.assertIn("background: var(--third-background-color);", source)
        self.assertIn("--waline-badge-color: var(--waline-theme-color);", source)
        self.assertNotIn("--waline-badge-color: #3498db;", source)
        self.assertIn(".internal-comments .wl-preview > hr", source)
        self.assertIn("border-top: 1px dashed var(--waline-border-color);", source)
        self.assertNotIn("--selected-highlight", palette)
        self.assertIn(":root[data-theme=\"dark\"] body.dark-mode", palette)
        self.assertIn("--highlight-background: inherit;", palette)

    def test_comment_records_request_metadata(self):
        response = self.client.post(
            reverse("comment_create", args=[self.article.slug]),
            {"nickname": "Guest", "content": "Hello"},
            HTTP_USER_AGENT="Mozilla/5.0 (Windows NT 10.0) AppleWebKit Chrome/120.0",
            REMOTE_ADDR="192.0.2.10",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()["comment"]
        self.assertEqual(payload["ip_address"], "192.0.2.10")
        self.assertEqual(Comment.objects.get(pk=payload["id"]).ip_address, "192.0.2.10")
        self.assertEqual(payload["browser"], "Chrome120.0")
        self.assertEqual(payload["operating_system"], "Windows 10")

    def test_comment_ip_is_visible_in_public_metadata(self):
        comment = Comment.objects.create(
            article=self.article,
            nickname="Guest",
            content="Hello",
            ip_address="192.0.2.44",
        )

        payload = self.client.get(
            reverse("comment_list", args=[self.article.slug])
        ).json()["comments"][0]

        self.assertEqual(payload["id"], comment.pk)
        self.assertEqual(payload["ip_address"], "192.0.2.44")

    def test_login_requirement_blocks_guest(self):
        self.site.comment_require_login = True
        self.site.save(update_fields=["comment_require_login"])
        response = self.client.post(
            reverse("comment_create", args=[self.article.slug]),
            {"nickname": "Guest", "content": "Hello"},
        )
        self.assertEqual(response.status_code, 401)

    def test_unapproved_comment_is_not_returned_to_the_page(self):
        self.site.comment_auto_approve = False
        self.site.save(update_fields=["comment_auto_approve"])
        response = self.client.post(
            reverse("comment_create", args=[self.article.slug]),
            {"nickname": "Guest", "content": "Needs review"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["pending"])
        self.assertEqual(self.client.get(reverse("comment_list", args=[self.article.slug])).json()["comments"], [])

    def test_registered_user_can_like_once(self):
        user = User.objects.create_user("reader", password="A-strong-password-123", email="reader@example.com")
        self.client.force_login(user)
        comment = Comment.objects.create(article=self.article, author=user, content="Hello")
        response = self.client.post(reverse("comment_like", args=[comment.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["liked"])
        self.assertEqual(comment.likes.count(), 1)

    def test_author_can_edit_and_delete_own_comment(self):
        user = User.objects.create_user("reader", password="A-strong-password-123")
        comment = Comment.objects.create(article=self.article, author=user, content="Original")
        self.client.force_login(user)
        response = self.client.post(reverse("comment_edit", args=[comment.id]), {"content": "Updated"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Comment.objects.get(pk=comment.id).content, "Updated")
        self.client.post(reverse("comment_delete", args=[comment.id]))
        self.assertFalse(Comment.objects.filter(pk=comment.id).exists())

    def test_staff_cannot_edit_another_users_comment_from_the_frontend(self):
        author = User.objects.create_user("comment-author", password="A-strong-password-123")
        staff = User.objects.create_user("comment-staff", password="A-strong-password-123", is_staff=True)
        staff.user_permissions.add(Permission.objects.get(codename="delete_comment"))
        comment = Comment.objects.create(article=self.article, author=author, content="Original")
        self.client.force_login(staff)

        payload = self.client.get(
            reverse("comment_list", args=[self.article.slug])
        ).json()["comments"][0]

        edit_response = self.client.post(
            reverse("comment_edit", args=[comment.pk]),
            {"content": "Staff rewrite"},
        )

        self.assertFalse(payload["can_edit"])
        self.assertTrue(payload["can_delete"])
        self.assertEqual(edit_response.status_code, 403)
        comment.refresh_from_db()
        self.assertEqual(comment.content, "Original")

    def test_article_comment_switch_blocks_list_and_create_endpoints(self):
        self.article.show_comment = False
        self.article.save(update_fields=("show_comment",))

        listing = self.client.get(reverse("comment_list", args=[self.article.slug]))
        creation = self.client.post(
            reverse("comment_create", args=[self.article.slug]),
            {"nickname": "Guest", "content": "Hidden endpoint"},
        )

        self.assertEqual(listing.status_code, 403)
        self.assertEqual(creation.status_code, 403)
        self.assertFalse(Comment.objects.exists())

    def test_logout_rejects_external_redirect_targets(self):
        user = User.objects.create_user("logout-reader", password="A-strong-password-123")
        self.client.force_login(user)

        response = self.client.post(
            reverse("comment_logout"),
            {"next": "https://evil.example/collect"},
        )

        self.assertRedirects(response, "/", fetch_redirect_response=False)

    @patch("blog.comment_views.EmailMultiAlternatives.send", side_effect=RuntimeError("mail down"))
    def test_failed_verification_email_rolls_back_registration(self, mock_send):
        response = self.client.post(
            reverse("comment_register_ajax"),
            {
                "username": "retryable-reader",
                "email": "retryable@example.com",
                "password": "A-strong-password-123",
                "password_confirm": "A-strong-password-123",
            },
        )

        self.assertEqual(response.status_code, 502)
        self.assertFalse(User.objects.filter(username="retryable-reader").exists())

    @override_settings(TRUST_X_FORWARDED_FOR=False)
    def test_untrusted_forwarded_address_is_not_stored(self):
        response = self.client.post(
            reverse("comment_create", args=[self.article.slug]),
            {"nickname": "Guest", "content": "Hello"},
            HTTP_X_FORWARDED_FOR="203.0.113.99",
            REMOTE_ADDR="192.0.2.30",
        )

        self.assertEqual(response.status_code, 200)
        comment_id = response.json()["comment"]["id"]
        self.assertEqual(response.json()["comment"]["ip_address"], "192.0.2.30")
        self.assertEqual(Comment.objects.get(pk=comment_id).ip_address, "192.0.2.30")

    def test_registration_rejects_a_password_similar_to_the_username(self):
        response = self.client.post(
            reverse("comment_register_ajax"),
            {
                "username": "distinctive-reader-name",
                "email": "similarity@example.com",
                "password": "distinctive-reader-name",
                "password_confirm": "distinctive-reader-name",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(username="distinctive-reader-name").exists())

    def test_unverified_login_explains_email_verification(self):
        User.objects.create_user("pending", password="A-strong-password-123", is_active=False)
        response = self.client.post(reverse("comment_login"), {"username": "pending", "password": "A-strong-password-123"})
        self.assertContains(response, "verification email")

    def test_guest_like_returns_json_error(self):
        comment = Comment.objects.create(article=self.article, nickname="Guest", content="Hello")
        response = self.client.post(reverse("comment_like", args=[comment.id]))
        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()["ok"])

    def test_comment_assets_are_scoped_to_active_site(self):
        response = self.client.get(reverse("comment_assets"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["emoji"], [])

    def test_configured_emoji_is_rendered_safely(self):
        pack = CommentEmojiPack.objects.create(config=self.site, name="Basic")
        CommentEmoji.objects.create(pack=pack, name="smile", image_url="https://cdn.example/smile.png")
        Comment.objects.create(article=self.article, nickname="Guest", content="Hi :smile:")
        response = self.client.get(reverse("comment_list", args=[self.article.slug]))
        self.assertIn("internal-comment-emoji", response.json()["comments"][0]["content_html"])

    def test_comment_assets_expose_waline_pack_tabs_in_order(self):
        first = CommentEmojiPack.objects.create(config=self.site, name="B站")
        CommentEmoji.objects.create(pack=first, name="bmoji_hot", image_url="https://cdn.example/hot.png", order=2)
        CommentEmoji.objects.create(pack=first, name="bmoji_doge", image_url="https://cdn.example/doge.png", order=1)
        second = CommentEmojiPack.objects.create(config=self.site, name="贴吧", order=1)
        CommentEmoji.objects.create(pack=second, name="tieba_1", image_url="https://cdn.example/tieba.png")
        payload = self.client.get(reverse("comment_assets")).json()
        self.assertEqual([pack["name"] for pack in payload["emoji"]], ["B站", "贴吧"])
        self.assertEqual([item["name"] for item in payload["emoji"][0]["items"]], ["bmoji_doge", "bmoji_hot"])
        self.assertEqual(payload["emoji"][0]["icon"], "https://cdn.example/doge.png")

    def test_giphy_api_key_is_not_exposed_in_comment_assets(self):
        CommentGifSource.objects.create(
            config=self.site,
            name="Giphy",
            endpoint="https://api.giphy.com/v1/gifs/search?api_key=secret",
        )
        endpoint = self.client.get(reverse("comment_assets")).json()["gif"][0]["endpoint"]
        self.assertIn("/api/comment-gif-proxy/", endpoint)
        self.assertNotIn("secret", endpoint)

    @patch("blog.comment_views.urlopen")
    def test_giphy_proxy_returns_data_array_as_results(self, mock_urlopen):
        source = CommentGifSource.objects.create(
            config=self.site,
            name="Giphy",
            endpoint="https://api.giphy.com/v1/gifs/search?api_key=test",
        )
        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return b'{"data":[{"images":{"original":{"url":"https://media.giphy.com/test.gif"}}}]}'
        mock_urlopen.return_value = FakeResponse()
        response = self.client.get(reverse("comment_gif_proxy"), {"source": source.pk, "q": "hello"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["results"]), 1)

    @patch("blog.comment_views.urlopen")
    def test_giphy_proxy_caps_provider_limit(self, mock_urlopen):
        source = CommentGifSource.objects.create(
            config=self.site,
            name="Giphy",
            endpoint="https://api.giphy.com/v1/gifs/search?api_key=test&limit=999",
        )

        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return b'{"data":[]}'

        mock_urlopen.return_value = FakeResponse()
        response = self.client.get(reverse("comment_gif_proxy"), {"source": source.pk, "q": "hello"})
        self.assertEqual(response.status_code, 200)
        request_url = mock_urlopen.call_args.args[0].full_url
        self.assertIn("limit=50", request_url)

    def test_comment_sanitizer_rejects_protocol_relative_urls(self):
        response = self.client.post(
            reverse("comment_create", args=[self.article.slug]),
            {"nickname": "Guest", "content": "![image](//evil.example/x.png)"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("evil.example", response.json()["comment"]["content_html"])

    def test_comment_preserves_safe_waline_markup_and_removes_scripts(self):
        response = self.client.post(
            reverse("comment_create", args=[self.article.slug]),
            {"nickname": "Guest", "content": '<font color="Crimson">Important</font><img class="wl-emoji" src="https://cdn.example/love.png"><script>alert(1)</script>'},
        )
        self.assertEqual(response.status_code, 200)
        html = response.json()["comment"]["content_html"]
        self.assertIn('<font color="Crimson">Important</font>', html)
        self.assertIn('class="wl-emoji"', html)
        self.assertNotIn("alert(1)", html)

    def test_uploaded_style_images_are_not_marked_as_emoji(self):
        response = self.client.post(
            reverse("comment_create", args=[self.article.slug]),
            {"nickname": "Guest", "content": "![image](/resources/comment-images/example.png)"},
        )
        self.assertEqual(response.status_code, 200)
        html = response.json()["comment"]["content_html"]
        self.assertIn('class="internal-comment-image"', html)
        self.assertNotIn('class="wl-emoji"', html)

    def test_registered_comment_is_marked_verified(self):
        user = User.objects.create_user("verified-reader", password="A-strong-password-123")
        Comment.objects.create(article=self.article, author=user, content="Hello")
        self.client.force_login(user)
        payload = self.client.get(reverse("comment_list", args=[self.article.slug])).json()["comments"][0]
        self.assertTrue(payload["verified"])

    def test_staff_can_toggle_comment_sticky(self):
        admin = User.objects.create_user("admin", password="A-strong-password-123", is_staff=True)
        admin.user_permissions.add(Permission.objects.get(codename="change_comment"))
        comment = Comment.objects.create(article=self.article, nickname="Guest", content="Hello")
        self.client.force_login(admin)
        response = self.client.post(reverse("comment_sticky", args=[comment.id]))
        self.assertEqual(response.status_code, 200)
        comment.refresh_from_db()
        self.assertTrue(comment.is_sticky)

    def test_staff_cannot_pin_two_comments_in_one_article(self):
        admin = User.objects.create_user("pin-admin", password="A-strong-password-123", is_staff=True)
        admin.user_permissions.add(Permission.objects.get(codename="change_comment"))
        first = Comment.objects.create(article=self.article, nickname="First", content="First")
        second = Comment.objects.create(article=self.article, nickname="Second", content="Second")
        self.client.force_login(admin)
        self.assertEqual(self.client.post(reverse("comment_sticky", args=[first.id])).status_code, 200)
        response = self.client.post(reverse("comment_sticky", args=[second.id]))
        self.assertEqual(response.status_code, 409)
        self.assertIn("Only one comment can be pinned", response.json()["error"])
        self.assertFalse(Comment.objects.get(pk=second.id).is_sticky)

    def test_comment_badge_assignment_is_exposed(self):
        user = User.objects.create_user("badge-reader", password="A-strong-password-123")
        badge = CommentBadge.objects.create(config=self.site, name="Contributor", color="#27ae60")
        CommentBadgeAssignment.objects.create(user=user, badge=badge)
        Comment.objects.create(article=self.article, author=user, content="Hello")
        self.client.force_login(user)
        payload = self.client.get(reverse("comment_list", args=[self.article.slug])).json()["comments"][0]
        self.assertEqual(payload["badges"], [{"name": "Contributor", "color": "#27ae60"}])

    def test_comment_badge_without_color_inherits_theme(self):
        user = User.objects.create_user("theme-badge-reader", password="A-strong-password-123")
        badge = CommentBadge.objects.create(config=self.site, name="Theme badge", color="")
        CommentBadgeAssignment.objects.create(user=user, badge=badge)
        Comment.objects.create(article=self.article, author=user, content="Hello")
        self.client.force_login(user)
        payload = self.client.get(reverse("comment_list", args=[self.article.slug])).json()["comments"][0]
        self.assertEqual(payload["badges"], [{"name": "Theme badge", "color": ""}])

    def test_internal_provider_uses_our_native_comment_frontend(self):
        html = render_to_string(
            "components/comments/comment.html",
            {"site": self.site, "article": self.article, "comment_system_configured": True},
        )
        self.assertIn("internal-comments", html)
        self.assertIn("internal.js", html)

    @override_settings(
        AUTHENTICATION_BACKENDS=(
            "django.contrib.auth.backends.ModelBackend",
            "django.contrib.auth.backends.AllowAllUsersModelBackend",
        )
    )
    def test_registration_requires_email_verification_by_default(self):
        response = self.client.post(
            reverse("comment_register"),
            {
                "username": "new-reader",
                "email": "new-reader@example.com",
                "password": "A-strong-password-123",
                "password_confirm": "A-strong-password-123",
            },
        )
        self.assertEqual(response.status_code, 200)
        user = User.objects.get(username="new-reader")
        self.assertFalse(user.is_active)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        verify_response = self.client.get(reverse("comment_verify", args=[uid, token]))
        self.assertEqual(verify_response.status_code, 200)
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        verify_response = self.client.post(reverse("comment_verify", args=[uid, token]))
        self.assertEqual(verify_response.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.is_active)


class ArchivePageTests(TestCase):
    def test_archive_renders_all_posts_without_home_sticky_ordering(self):
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
    def test_json_label_list_is_supported(self):
        self.assertEqual(get_author_label(8, False, ["New", "Regular"]), "Regular")


class RedefineParityTests(TestCase):
    def setUp(self):
        cache.clear()
        self.site = SiteConfiguration.objects.create(
            config_name="Parity",
            site_name="Parity site",
            is_active=True,
        )

    def test_home_metadata_switches_do_not_hide_article_metadata(self):
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
        self.assertEqual(article._categories_meta(self.site, limited=False)[0]["name"], "News")
        self.assertEqual(article._tags_meta(self.site, limited=False)[0]["name"], "Django")

    def test_zero_home_metadata_limits_mean_unlimited(self):
        self.site.article_categories_limit = 0
        self.site.article_tags_limit = 0
        self.site.full_clean()

    def test_auto_home_date_starts_absolute_for_old_posts(self):
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

    def test_custom_moment_style_home_date_format_is_supported(self):
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

    def test_second_home_page_is_not_marked_as_banner_first_page(self):
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

    def test_social_center_layout_hides_scroll_button(self):
        self.site.social_links_enabled = True
        self.site.social_links_style = "center"
        html = render_to_string("pages/home/home-banner.html", {"site": self.site})

        self.assertIn('class="hidden p-3', html)

    def test_social_image_uses_its_name_as_icon_and_url_as_destination(self):
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

    def test_mobile_sidebar_does_not_repeat_navbar_links(self):
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

    def test_footer_statistics_and_website_counter_are_independent(self):
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

    def test_article_open_graph_uses_page_metadata_and_absolute_image(self):
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

    def test_home_thumbnail_and_article_cover_keep_upstream_priority(self):
        article = ArticleModel(
            thumbnail=SimpleUploadedFile("thumbnail.png", b"thumbnail"),
            cover=SimpleUploadedFile("cover.png", b"cover"),
            banner=SimpleUploadedFile("banner.png", b"banner"),
        )

        self.assertTrue(article.thumbnail_url.endswith("thumbnail.png"))
        self.assertTrue(article.article_cover_url.endswith("cover.png"))

    def test_article_dates_match_redefine_compact_format(self):
        midnight = timezone.make_aware(
            datetime(1900, 1, 1, 0, 0, 0)
        )
        whole_minute = timezone.make_aware(
            datetime(2026, 10, 25, 14, 6, 0)
        )
        article = ArticleModel(created_at=midnight)
        article.updated_at = whole_minute

        self.assertEqual(article.created_at_display, "1900-01-01")
        self.assertEqual(article.updated_at_display, "2026-10-25 14:06")
        self.assertTrue(article.has_meaningful_update)

    def test_immediate_update_time_is_not_repeated(self):
        created = timezone.now()
        article = ArticleModel(created_at=created)
        article.updated_at = created + timedelta(milliseconds=500)

        self.assertFalse(article.has_meaningful_update)

    def test_long_home_pagination_uses_compact_gaps(self):
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

    def test_cloud_tag_page_matches_upstream_hundred_tag_limit(self):
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

    def test_mobile_nav_uses_same_translated_uppercase_label_as_desktop(self):
        MenuLink.objects.create(
            config=self.site,
            link_location="navbar",
            name="Home",
            url="/",
        )

        response = self.client.get(reverse("index"), HTTP_ACCEPT_LANGUAGE="zh-CN")

        self.assertGreaterEqual(response.content.decode().count("首页"), 2)

    def test_empty_preloader_message_falls_back_to_site_title(self):
        self.site.preloader_message = ""

        html = render_to_string(
            "components/header/preloader.html",
            {"site": self.site},
        )

        self.assertIn("Parity site", html)

    def test_emergency_config_creation_uses_project_identity_defaults(self):
        SiteConfiguration.objects.all().delete()
        cache.clear()

        site = SiteConfiguration.load()

        self.assertEqual(site.site_name, "Django Redefine")
        self.assertEqual(site.preloader_message, "")

    def test_bookmark_page_exposes_controller_scope(self):
        StandalonePage.objects.filter(
            config=self.site, page_type=StandalonePage.BOOKMARKS
        ).update(enabled=True)
        cache.clear()

        response = self.client.get(reverse("bookmarks"))

        self.assertContains(response, 'class="bookmarks-page py-8 sm:py-0"')

    def test_bookmark_controller_selects_the_current_category(self):
        script = (
            Path(__file__).parent / "static" / "js" / "layouts" / "bookmarkNav.js"
        ).read_text(encoding="utf-8")
        main_script = (
            Path(__file__).parent / "static" / "js" / "main.js"
        ).read_text(encoding="utf-8")
        stylesheet = (
            Path(__file__).parent / "static" / "css" / "style.css"
        ).read_text(encoding="utf-8")

        self.assertIn('item.classList.toggle(\n                "active"', script)
        self.assertIn('import initBookmarkNav from "./layouts/bookmarkNav.js";', main_script)
        self.assertIn("initBookmarkNav();", main_script)
        self.assertIn(".bookmark-nav-item.active {", stylesheet)
        self.assertIn("background-color: var(--second-background-color);", stylesheet)
        self.assertNotIn(".bookmarks-page .bookmark-card-link:hover", stylesheet)

    def test_profile_keeps_password_rules_bulleted_but_not_red_errors(self):
        stylesheet = (
            Path(__file__).parent / "static" / "css" / "profile.css"
        ).read_text(encoding="utf-8")

        self.assertIn(".profile-help ul { margin: 4px 0 0; padding-left: 1.25rem; }", stylesheet)
        self.assertIn(".profile-field-errors .errorlist", stylesheet)
        self.assertIn("list-style: none !important", stylesheet)

    def test_delete_account_link_has_no_hover_animation(self):
        stylesheet = (
            Path(__file__).parent / "static" / "css" / "profile.css"
        ).read_text(encoding="utf-8")

        self.assertIn(
            ".profile-delete-link:hover { border-color: #b42318; color: #fff; background: #b42318; }",
            stylesheet,
        )

    def test_info_first_sidebar_keeps_upstream_card_spacing(self):
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

    def test_manual_home_excerpt_is_rendered_as_markdown(self):
        article = ArticleModel.objects.create(
            title="Excerpt",
            excerpt="A **formatted** [link](https://example.com).",
            content="Body",
            is_published=True,
        )

        rendered = str(article.auto_excerpt)

        self.assertIn("<strong>formatted</strong>", rendered)
        self.assertIn('href="https://example.com"', rendered)


class FrontendScriptTests(TestCase):
    def test_project_layout_options_are_not_database_fields(self):
        for field_name in (
            "content_max_width",
            "toc_sidebar_width",
            "navbar_width_home",
            "navbar_width_pages",
            "article_font_size",
            "article_line_height",
            "article_image_border_radius",
            "heading_h1_top_spacing",
        ):
            with self.assertRaises(FieldDoesNotExist):
                SiteConfiguration._meta.get_field(field_name)

    def test_article_tabs_are_loaded_when_toc_is_disabled(self):
        site = SiteConfiguration(toc_enabled=False)
        html = render_to_string("components/scripts.html", {"site": site})
        self.assertIn("js/plugins/tabs.js", html)
        self.assertNotIn("js/layouts/toc.js", html)

    def test_article_tabs_and_main_entry_are_loaded_once_when_toc_is_enabled(self):
        site = SiteConfiguration(toc_enabled=True)
        html = render_to_string("components/scripts.html", {"site": site})
        self.assertEqual(html.count("js/plugins/tabs.js"), 1)
        self.assertEqual(html.count("js/main.js"), 1)
        # main imports the TOC module through utils, so a second script tag
        # would register a duplicate page lifecycle
        self.assertNotIn("js/layouts/toc.js", html)

    @override_settings(
        SITE_CONTENT_MAXWIDTH=960,
        SITE_SIDEBAR_WIDTH=230,
        NAVBAR_WIDTH={"home": 1180, "pages": 940},
        ARTICLE_FONT_SIZE=18,
        ARTICLE_LINE_HEIGHT=1.7,
        ARTICLE_IMG_BORDER_RADIUS=12,
        ARTICLE_HEADINGS_TOP_SPACING={
            "h1": "3rem",
            "h2": "2rem",
            "h3": "1.8rem",
            "h4": "1.5rem",
            "h5": "1.3rem",
            "h6": "1.1rem",
        },
    )
    def test_theme_overrides_use_project_layout_and_site_colours(self):
        site = SiteConfiguration(
            navbar_lcolor="#112233",
            navbar_rcolor="#abcdef",
            navbar_transparency=40,
        )
        context = site_processor(RequestFactory().get("/"))
        context["site"] = site
        html = render_to_string(
            "components/header/theme-overrides.html", context
        )
        self.assertIn("--site-content-max-width: 960px", html)
        self.assertIn("--site-toc-sidebar-width: 230px", html)
        self.assertIn("--site-navbar-width-home: 1180px", html)
        self.assertIn("rgba(17, 34, 51, 0.251)", html)
        self.assertIn("rgba(171, 205, 239, 0.251)", html)
        self.assertIn("--site-article-font-size: 18px", html)
        self.assertIn("--site-article-line-height: 1.7", html)
        self.assertIn("margin-top: 2rem", html)
        self.assertIn("html.theme-switching *", html)
        self.assertIn("transition-duration: 0s !important", html)
        self.assertIn("::view-transition-new(root)", html)
        self.assertIn("theme-fade-in", html)

    def test_multiline_template_comment_is_not_rendered(self):
        site = SiteConfiguration.objects.create(
            config_name="Template comment theme",
            colour_default_mode="light",
        )
        html = render_to_string("components/header/head.html", {"site": site})
        self.assertNotIn("{#", html)
        self.assertNotIn("Redefine's browser modules consume", html)

    def test_site_identity_analytics_and_icp_come_from_site_configuration(self):
        site = SiteConfiguration.objects.create(
            config_name="Admin-owned site identity",
            site_name="Admin Site",
            site_subname="Admin Subtitle",
            site_author="Admin Author",
            site_description="Admin Description",
            site_keywords="admin,site",
            google_analytics_enabled=True,
            google_analytics_id="G-TEST123",
            show_icp=True,
            icp_number="ICP 12345678",
            icp_url="https://beian.miit.gov.cn/",
        )
        request = RequestFactory().get("/")
        head = render_to_string(
            "components/header/head.html",
            {"site": site, "request": request, "SITE_LANG": "zh-CN"},
        )
        footer = render_to_string(
            "components/footer/footer.html",
            {
                "site": site,
                "articles_count": 0,
                "total_words": 0,
                "site_uv": 0,
                "site_pv": 0,
            },
        )

        self.assertIn('content="admin,site"', head)
        self.assertIn('content="Admin Description"', head)
        self.assertIn('content="Admin Author"', head)
        self.assertIn("G-TEST123", head)
        self.assertIn("Admin Site - Admin Subtitle", head)
        self.assertIn("ICP 12345678", footer)


class RedefineMarkdownTests(TestCase):
    def render(
        self,
        source,
        *,
        image_caption=False,
        lazyload=False,
        mermaid=False,
        delete_mask=False,
    ):
        site = SiteConfiguration(
            hyperlink_icon=True,
            article_image_description=image_caption,
            article_lazyload=lazyload,
            mermaid_enabled=mermaid,
            delete_mask=delete_mask,
        )
        return Markdown(extensions=get_extensions(site)).convert(source)

    def test_small_and_large_notes_render_markdown(self):
        small = self.render(
            "{% note warning fa-circle-exclamation %}\n**Careful**\n{% endnote %}"
        )
        large = self.render(
            "{% notel info fa-circle-info Details %}\nA [link](https://external.invalid).\n{% endnotel %}"
        )

        self.assertIn('class="note p-4 mb-4 rounded-small markdown-body warning icon-padding"', small)
        self.assertIn('class="note-icon fa-solid fa-circle-exclamation"', small)
        self.assertIn("<strong>Careful</strong>", small)
        self.assertIn('class="note-large info"', large)
        self.assertIn("<p>Details</p>", large)
        self.assertIn('class="link"', large)

    def test_large_note_aliases_and_default_title_match_redefine(self):
        aliases = ("noteL", "notel", "notelarge", "notel-large", "notes-large", "subwarning")
        for alias in aliases:
            with self.subTest(alias=alias):
                html = self.render(
                    f"{{% {alias} %}}\nBody\n{{% end{alias} %}}"
                )
                self.assertIn('class="note-large default"', html)
                self.assertIn("<p>Warning</p>", html)
                self.assertIn("<p>Body</p>", html)

        markdown_title = self.render(
            "{% notel info **Important** %}\nBody\n{% endnotel %}"
        )
        self.assertIn("<p><strong>Important</strong></p>", markdown_title)

    def test_tabs_keep_redefine_dom_and_active_order(self):
        html = self.render(
            "{% tabs Demo,2 %}\n"
            "<!-- tab First -->\nFirst pane\n<!-- endtab -->\n"
            "<!-- tab Second -->\n**Second pane**\n<!-- endtab -->\n"
            "{% endtabs %}"
        )

        self.assertIn('<div class="tabs" id="tab-demo">', html)
        self.assertIn('<ul class="nav-tabs">', html)
        self.assertIn('<li class="tab"><a class="#demo-1">First</a></li>', html)
        self.assertIn('<li class="tab active"><a class="#demo-2">Second</a></li>', html)
        self.assertIn('<div class="tab-pane active" id="demo-2">', html)
        self.assertIn("<strong>Second pane</strong>", html)

    def test_tab_markers_inside_long_code_fences_remain_code(self):
        html = self.render(
            "````html\n"
            "<!-- tab Not a tab -->\n"
            "```\n"
            "<!-- endtab -->\n"
            "````"
        )

        self.assertNotIn('<div class="tabs"', html)
        self.assertIn("Not a tab", html)

    def test_tabs_render_header_html_and_nested_subtabs(self):
        html = self.render(
            "{% tabs Outer %}\n"
            "<!-- tab First@<i class='fa-solid fa-book'></i> -->\n"
            "{% subtabs Inner %}\n"
            "<!-- tab Nested -->\nNested content\n<!-- endtab -->\n"
            "{% endsubtabs %}\n"
            "<!-- endtab -->\n"
            "{% endtabs %}"
        )

        self.assertIn("fa-solid fa-book", html)
        self.assertIn("</i>First", html)
        self.assertIn('<div class="tabs" id="tab-outer">', html)
        self.assertIn('<div class="tabs" id="tab-inner">', html)
        self.assertIn("Nested content", html)

    def test_folding_and_buttons_match_redefine_structure(self):
        folding = self.render(
            "{% folding blue::More %}\n## Hidden heading\n{% endfolding %}"
        )
        buttons = self.render(
            "{% btn primary::Docs::https://example.com::fa-solid fa-book %}\n\n"
            "{% btns rounded %}\n"
            "{% cell Home::/::fa-solid fa-house %}\n"
            "{% cell Picture::/picture::/icon.png %}\n"
            "{% endbtns %}"
        )

        self.assertIn('<details class="blue" data-header-exclude="">', folding)
        self.assertIn('<p class="h2">Hidden heading</p>', folding)
        self.assertIn('class="button primary"', buttons)
        self.assertIn('class="btns rounded"', buttons)
        self.assertIn('class="fa-solid fa-house"', buttons)
        self.assertIn('<img src="/icon.png"', buttons)

    def test_image_captions_follow_site_setting(self):
        source = "![Landscape](/images/landscape.png)"
        disabled = self.render(source, image_caption=False)
        enabled = self.render(source, image_caption=True)

        self.assertNotIn("image-caption", disabled)
        self.assertIn('<figure class="image-caption">', enabled)
        self.assertIn("<figcaption>Landscape</figcaption>", enabled)

    def test_lazyload_uses_redefine_placeholder_attributes(self):
        source = "![Landscape](/images/landscape.png)"
        disabled = self.render(source, lazyload=False)
        enabled = self.render(source, lazyload=True)

        self.assertIn('src="/images/landscape.png"', disabled)
        self.assertIn('lazyload=""', enabled)
        self.assertIn('src="/static/images/loading.svg"', enabled)
        self.assertIn('data-src="/images/landscape.png"', enabled)

    def test_raw_html_images_receive_caption_and_lazyload_filters(self):
        html = self.render(
            '<img class="hero" src="/images/raw.png" alt="Raw image">',
            image_caption=True,
            lazyload=True,
        )

        self.assertIn('<figure class="image-caption">', html)
        self.assertIn('class="hero"', html)
        self.assertIn('lazyload=""', html)
        self.assertIn('src="/static/images/loading.svg"', html)
        self.assertIn('data-src="/images/raw.png"', html)
        self.assertIn('<figcaption>Raw image</figcaption>', html)

    def test_mermaid_fences_become_diagrams_only_when_plugin_is_enabled(self):
        source = "```mermaid\ngraph TD\n  A --> B\n```"
        disabled = self.render(source, mermaid=False)
        enabled = self.render(source, mermaid=True)

        self.assertIn('class="iseeu highlight mermaid"', disabled)
        self.assertIn('<pre class="mermaid">graph TD\n  A --&gt; B</pre>', enabled)
        self.assertNotIn('code-container', enabled)

    def test_fenced_code_supports_tildes_long_fences_and_embedded_markers(self):
        tildes = self.render("~~~python\nprint('ok')\n~~~")
        long_fence = self.render("````text\n``` is content\n````")
        trailing = self.render("```text\nvalue\n```\n\nAfter")

        self.assertIn('data-language="python"', tildes)
        self.assertIn('class="hljs-variable">print</span>', tildes)
        self.assertIn('class="hljs-string">ok</span>', tildes)
        self.assertIn("``` is content", long_fence)
        self.assertIn("<p>After</p>", trailing)

    def test_strikethrough_and_delete_mask_share_the_markdown_pipeline(self):
        plain = self.render("~~hidden~~ and <del>raw</del>")
        masked = self.render("~~hidden~~ and <del>raw</del>", delete_mask=True)

        self.assertIn("<del>hidden</del>", plain)
        self.assertIn("<del>raw</del>", plain)
        self.assertIn('<del class="mask">hidden</del>', masked)
        self.assertIn('<del class="mask">raw</del>', masked)

    @override_settings(ALLOWED_HOSTS=["blog.example.com"])
    def test_link_icons_only_decorate_external_text_links(self):
        html = self.render(
            "[internal](https://blog.example.com/about) "
            "[subdomain](https://static.blog.example.com/file) "
            "[external](https://example.net) "
            "[![image](/image.png)](https://example.net/image)"
        )

        self.assertNotIn('href="https://blog.example.com/about" rel=', html)
        self.assertNotIn('href="https://static.blog.example.com/file" rel=', html)
        self.assertIn(
            'class="link" href="https://example.net" rel="noopener" target="_blank"',
            html,
        )
        self.assertEqual(html.count('class="link"'), 1)

    def test_gfm_task_lists_render_accessible_checkboxes(self):
        html = self.render("- [x] shipped **now**\n- [ ] pending")

        self.assertIn('<ul class="contains-task-list">', html)
        self.assertEqual(html.count('class="task-list-item"'), 2)
        self.assertIn('checked="checked"', html)
        self.assertEqual(html.count('disabled="disabled"'), 2)
        self.assertRegex(html, r'<input[^>]+ /> shipped <strong>now</strong>')

    def test_unclosed_redefine_tag_does_not_consume_following_markdown(self):
        html = self.render("{% note warning %}\nVisible\n\n## Still here")

        self.assertIn("{% note warning %}", html)
        self.assertIn("Visible", html)
        self.assertIn("Still here", html)

    def test_runtime_theme_options_come_from_site_configuration(self):
        site = SiteConfiguration.objects.create(
            config_name="Runtime theme options",
            article_lazyload=False,
            article_pangu_js=True,
        )
        head = render_to_string("components/header/head.html", {"site": site})
        scripts = render_to_string("components/scripts.html", {"site": site})

        self.assertNotIn("preload:", head)
        self.assertIn('path: "/search.json"', head)
        self.assertIn("lazyload: false", head)
        self.assertIn("js/libs/pangu.min.js", scripts)


class NotFoundPageTests(TestCase):
    @override_settings(DEBUG=False)
    def test_unknown_route_uses_redefine_not_found_page(self):
        SiteConfiguration.objects.create(
            config_name="404 theme",
            site_name="Test site",
            is_active=True,
        )
        response = self.client.get("/route-that-does-not-exist/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Page Not Found", status_code=404)
        self.assertContains(response, "nf-container", status_code=404)


class AdminExperienceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            "dashboard-admin",
            "admin@example.com",
            "A-strong-password-123",
        )
        self.site = SiteConfiguration.objects.create(
            config_name="Admin theme",
            site_name="Admin test site",
            is_active=True,
        )
        self.client.force_login(self.user)

    def configuration_form_data(self, **updates):
        data = model_to_dict(self.site)
        for field_name in (
            "subtitle_text",
            "author_label_list",
            "recommendation_skip_dirs",
            "aplayer_config",
        ):
            data[field_name] = json.dumps(data[field_name])
        data.update({
            "waline_emoji": "[]",
            "waline_reaction": "[]",
        })
        data.update(updates)
        return data

    def test_site_configuration_admin_exposes_every_model_field(self):
        visible = set()
        for _, options in SiteConfigurationAdmin.fieldsets:
            for item in options.get("fields", ()):
                visible.update(item if isinstance(item, (tuple, list)) else (item,))

        editable = {
            field.name
            for field in SiteConfiguration._meta.fields
            if field.editable and not field.auto_created
        }
        self.assertEqual(
            editable - visible,
            {
                "comment_config",
                "navbar_search_preload",
                "bookmarks_enabled",
                "essays_enabled",
                "masonry_enabled",
                "friends_enabled",
                "friends_page_columns",
                "tags_page_style",
            },
        )

    def test_admin_filters_only_cover_useful_list_workflows(self):
        self.assertEqual(SiteConfigurationAdmin.list_filter, ("is_active", "comment_system"))
        self.assertEqual(
            ArticleAdmin.list_filter,
            ("is_published", "created_at", "category", "tags"),
        )
        self.assertEqual(FriendCategoryAdmin.list_filter, ())

    def test_admin_filter_groups_render_collapsed_by_default(self):
        response = self.client.get(reverse("admin:blog_siteconfiguration_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<details data-filter-title="comment system">')
        self.assertNotContains(response, '<details data-filter-title="comment system" open>')
        self.assertNotContains(response, "homebanner enabled")
        self.assertNotContains(response, "comment enabled")

    def test_comment_provider_validation_happens_before_save(self):
        form = SiteConfigurationForm(
            data=self.configuration_form_data(
                comment_enabled=True,
                comment_system="waline",
                waline_server_url="",
                waline_emoji='{"not": "an array"}',
            ),
            instance=self.site,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("waline_server_url", form.errors)
        self.assertIn("waline_emoji", form.errors)

    def test_switching_comment_provider_preserves_other_provider_settings(self):
        self.site.comment_config = {
            "gitalk": {"repo": "preserved-repository"},
            "waline": {"serverUrl": "https://old.example.com"},
        }
        self.site.save()
        form = SiteConfigurationForm(
            data=self.configuration_form_data(
                comment_enabled=True,
                comment_system="waline",
                waline_server_url="https://comments.example.com",
            ),
            instance=self.site,
        )

        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(saved.comment_config["gitalk"]["repo"], "preserved-repository")
        self.assertEqual(saved.comment_config["waline"]["serverUrl"], "https://comments.example.com")

    def test_admin_dashboard_and_configuration_search_assets_render(self):
        self.site.colour_primary = "#245678"
        self.site.save(update_fields=("colour_primary",))
        dashboard = self.client.get(reverse("admin:index"))
        configuration = self.client.get(
            reverse("admin:blog_siteconfiguration_change", args=(self.site.pk,))
        )

        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, "redefine-dashboard-summary")
        self.assertContains(dashboard, "Visits today")
        self.assertNotContains(dashboard, "CONTROL CENTER")
        self.assertContains(dashboard, "css/admin/redefine-admin.css")
        self.assertContains(dashboard, "--redefine-admin-accent: #245678;")
        self.assertEqual(configuration.status_code, 200)
        self.assertContains(configuration, "js/admin/redefine-admin.js")
        self.assertContains(configuration, "Edit site configuration")
        self.assertContains(configuration, "Configuration")
        self.assertNotContains(configuration, "📂")
        self.assertContains(configuration, "recommendation_mobile_limit")
        self.assertContains(configuration, "sidetools_auto_expand")
