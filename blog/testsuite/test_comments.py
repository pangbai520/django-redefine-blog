import base64
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template.loader import render_to_string
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from ..models import (
    ArticleModel,
    Comment,
    CommentBadge,
    CommentBadgeAssignment,
    CommentBadgeTranslation,
    CommentEmoji,
    CommentEmojiPack,
    CommentGifSource,
    CommentImage,
    SiteConfiguration,
)

User = get_user_model()


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

    def test_guest_created(self):
        response = self.client.post(
            reverse("comment_create", args=[self.article.slug]),
            {"nickname": "Guest", "content": "Hello"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Comment.objects.count(), 1)
        self.assertEqual(response.json()["comment"]["author"], "Guest")

    def test_login_up(self):
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
        self.assertContains(response, "data-msg-comment-length=")
        self.assertContains(response, 'data-authenticated="false"')
        self.assertContains(response, 'data-comment-require-login="true"')
        self.assertContains(response, "data-comment-toasts")
        self.assertContains(response, "data-comment-confirm")
        self.assertContains(response, 'class="internal-auth-heading-icon"')
        self.assertContains(response, "fa-solid fa-right-to-bracket")
        self.assertContains(response, "fa-solid fa-user-plus")
        self.assertContains(response, "fa-solid fa-envelope")
        self.assertContains(response, "fa-solid fa-shield-halved")
        self.assertNotContains(response, 'class="internal-auth-field"><i class=')

        source = (
            Path(__file__).parent.parent / "static" / "js" / "comments" / "internal.js"
        ).read_text(encoding="utf-8")
        self.assertIn('root.addEventListener("click"', source)
        self.assertIn('event.target.closest(".internal-auth-open")', source)
        self.assertIn("}, true);", source)
        self.assertIn(
            "setTimeout(function () { openAuthModal(requestedPanel); }, 0)", source
        )
        self.assertIn('root.dataset.authHandlerVersion = "delegated-v3"', source)

    def test_fenced_palette(self):
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

    def test_comment_pipeline(self):
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

    def test_comment_emoji(self):
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

    def test_username_panel(self):
        response = self.client.get(reverse("article", args=[self.article.slug]))
        html = response.content.decode()
        login_panel, register_panel = html.split('data-auth-panel="register"', 1)

        self.assertNotIn(
            "Your username cannot be changed after registration.", login_panel
        )
        self.assertIn(
            "Your username cannot be changed after registration.", register_panel
        )

    def test_badge_translation(self):
        user = User.objects.create_user(
            "translated-badge", password="A-strong-password-123"
        )
        badge = CommentBadge.objects.create(
            config=self.site, name="Owner", enabled=True
        )
        CommentBadgeTranslation.objects.update_or_create(
            badge=badge, language_code="zh-hans", defaults={"name": "博主"}
        )
        CommentBadgeAssignment.objects.create(user=user, badge=badge)
        Comment.objects.create(article=self.article, author=user, content="Hello")
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "zh-hans"

        payload = self.client.get(
            reverse("comment_list", args=[self.article.slug])
        ).json()

        self.assertEqual(payload["comments"][0]["badges"][0]["name"], "博主")

    def test_identical_object(self):
        user = User.objects.create_user(
            "dedupe-uploader", password="A-strong-password-123"
        )
        self.client.force_login(user)
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQABpfZFQAAAAABJRU5ErkJggg=="
        )

        with tempfile.TemporaryDirectory(
            dir=settings.BASE_DIR
        ) as media_root, override_settings(MEDIA_ROOT=media_root):
            first = self.client.post(
                reverse("comment_upload"),
                {
                    "image": SimpleUploadedFile(
                        "first.png", png, content_type="image/png"
                    )
                },
            )
            second = self.client.post(
                reverse("comment_upload"),
                {
                    "image": SimpleUploadedFile(
                        "second.png", png, content_type="image/png"
                    )
                },
            )

            self.assertEqual(first.json()["url"], second.json()["url"])
            self.assertEqual(first.json()["image_id"], second.json()["image_id"])
            self.assertEqual(CommentImage.objects.count(), 1)
            self.assertEqual(
                len(list(Path(media_root, "comment-images").glob("*.png"))), 1
            )

    def test_uploaded_reference(self):
        user = User.objects.create_user(
            "image-lifecycle", password="A-strong-password-123"
        )
        self.client.force_login(user)
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQABpfZFQAAAAABJRU5ErkJggg=="
        )

        with tempfile.TemporaryDirectory(
            dir=settings.BASE_DIR
        ) as media_root, override_settings(MEDIA_ROOT=media_root):
            first_upload = self.client.post(
                reverse("comment_upload"),
                {"image": SimpleUploadedFile("one.png", png, content_type="image/png")},
            ).json()
            first_response = self.client.post(
                reverse("comment_create", args=[self.article.slug]),
                {
                    "content": f"![image]({first_upload['url']})",
                    "image_ids": first_upload["image_id"],
                },
            )
            second_upload = self.client.post(
                reverse("comment_upload"),
                {"image": SimpleUploadedFile("two.png", png, content_type="image/png")},
            ).json()
            second_response = self.client.post(
                reverse("comment_create", args=[self.article.slug]),
                {
                    "content": f"![image]({second_upload['url']})",
                    "image_ids": second_upload["image_id"],
                },
            )
            first_comment = Comment.objects.get(
                pk=first_response.json()["comment"]["id"]
            )
            second_comment = Comment.objects.get(
                pk=second_response.json()["comment"]["id"]
            )
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

    def test_shared_comment(self):
        user = User.objects.create_user(
            "shared-image-owner", password="A-strong-password-123"
        )
        first_comment = Comment.objects.create(
            article=self.article, author=user, content="First reference"
        )
        second_comment = Comment.objects.create(
            article=self.article, author=user, content="Second reference"
        )

        with tempfile.TemporaryDirectory(
            dir=settings.BASE_DIR
        ) as media_root, override_settings(MEDIA_ROOT=media_root):
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

    @patch(
        "blog.comment_views.default_storage.url",
        return_value="/media/comment-images/test.png",
    )
    @patch(
        "blog.comment_views.default_storage.save",
        return_value="comment-images/test.png",
    )
    def test_comment_slug(self, _save, _url):
        user = User.objects.create_user("uploader", password="A-strong-password-123")
        self.client.force_login(user)
        # use a real one-pixel PNG, so byte validation is exercised instead of mocked
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQABpfZFQAAAAABJRU5ErkJggg=="
        )
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

    @patch(
        "blog.comment_views.default_storage.url",
        return_value="/media/comment-images/test.png",
    )
    @patch(
        "blog.comment_views.default_storage.save",
        return_value="comment-images/test.png",
    )
    def test_comment_content(self, _save, _url):
        user = User.objects.create_user("image-owner", password="A-strong-password-123")
        self.client.force_login(user)
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQABpfZFQAAAAABJRU5ErkJggg=="
        )
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

    def test_comment_bytes(self):
        user = User.objects.create_user(
            "invalid-uploader", password="A-strong-password-123"
        )
        self.client.force_login(user)
        response = self.client.post(
            reverse("comment_upload"),
            {
                "image": SimpleUploadedFile(
                    "test.png", b"not an image", content_type="image/png"
                )
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])

    def test_comment_guards(self):
        script = (
            Path(__file__).parent.parent / "static" / "js" / "comments" / "internal.js"
        )
        source = script.read_text(encoding="utf-8")
        # cover the interaction paths that previously regressed, so emoji/GIF
        # insertion, popup closing and like locking cannot silently break again
        for marker in (
            'insertAtCursor(node.querySelector(".wl-editor"), token)',
            'insertAtCursor(node.querySelector(".wl-editor"), gifMarkdown)',
            'if (!action && !event.target.closest(".internal-comment-picker"))',
            "if (sequence !== gifSearchSequence) return;",
            "if (likeButton && !likeButton.disabled)",
            "if (!isAuthenticated && commentRequiresLogin)",
            "if (!isAuthenticated)",
            'openAuthModal("login")',
            'showToast(error.message, "error")',
            "if (!content || content.length > 5000)",
            'node.dataset.submitting === "true"',
            'requestConfirmation(message("DeleteConfirm", "Delete this comment?"))',
            'replyNeedsAuth ? " internal-auth-open"',
            '!isAuthenticated ? " internal-auth-open"',
            "extractFencedCodeBlocks(value)",
            'fetch("/api/comments/preview/"',
        ):
            self.assertIn(marker, source)
        self.assertNotIn("alert(", source)
        self.assertNotIn("confirm(", source)

    @patch("blog.comment_views._rate_limited")
    def test_empty_limiting(self, rate_limited):
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

    def test_comment_palette(self):
        stylesheet = (
            Path(__file__).parent.parent / "static" / "css" / "internal-comments.css"
        )
        source = stylesheet.read_text(encoding="utf-8")
        palette = (
            Path(__file__).parent.parent / "static" / "css" / "codeblock-settings.css"
        ).read_text(encoding="utf-8")

        self.assertIn("background: var(--highlight-background);", source)
        self.assertIn("color: var(--highlight-foreground);", source)
        self.assertIn("background: var(--third-background-color);", source)
        self.assertIn("--waline-badge-color: var(--waline-theme-color);", source)
        self.assertNotIn("--waline-badge-color: #3498db;", source)
        self.assertIn(".internal-comments .wl-preview > hr", source)
        self.assertIn("border-top: 1px dashed var(--waline-border-color);", source)
        self.assertNotIn("--selected-highlight", palette)
        self.assertIn(':root[data-theme="dark"] body.dark-mode', palette)
        self.assertIn("--highlight-background: inherit;", palette)

    def test_comment_metadata(self):
        response = self.client.post(
            reverse("comment_create", args=[self.article.slug]),
            {"nickname": "Guest", "content": "Hello"},
            HTTP_USER_AGENT="Mozilla/5.0 (Windows NT 10.0) AppleWebKit Chrome/120.0",
            REMOTE_ADDR="192.0.2.10",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()["comment"]
        self.assertEqual(payload["ip_address"], "")
        self.assertEqual(Comment.objects.get(pk=payload["id"]).ip_address, "192.0.2.10")
        self.assertEqual(payload["browser"], "Chrome120.0")
        self.assertEqual(payload["operating_system"], "Windows 10")

    def test_comment_metadata2(self):
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
        self.assertEqual(payload["ip_address"], "")

    def test_login_guest(self):
        self.site.comment_require_login = True
        self.site.save(update_fields=["comment_require_login"])
        response = self.client.post(
            reverse("comment_create", args=[self.article.slug]),
            {"nickname": "Guest", "content": "Hello"},
        )
        self.assertEqual(response.status_code, 401)

    def test_unapproved_page(self):
        self.site.comment_auto_approve = False
        self.site.save(update_fields=["comment_auto_approve"])
        response = self.client.post(
            reverse("comment_create", args=[self.article.slug]),
            {"nickname": "Guest", "content": "Needs review"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["pending"])
        self.assertEqual(
            self.client.get(reverse("comment_list", args=[self.article.slug])).json()[
                "comments"
            ],
            [],
        )

    def test_registered_once(self):
        user = User.objects.create_user(
            "reader", password="A-strong-password-123", email="reader@example.com"
        )
        self.client.force_login(user)
        comment = Comment.objects.create(
            article=self.article, author=user, content="Hello"
        )
        response = self.client.post(reverse("comment_like", args=[comment.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["liked"])
        self.assertEqual(comment.likes.count(), 1)

    def test_author_comment(self):
        user = User.objects.create_user("reader", password="A-strong-password-123")
        comment = Comment.objects.create(
            article=self.article, author=user, content="Original"
        )
        self.client.force_login(user)
        response = self.client.post(
            reverse("comment_edit", args=[comment.id]), {"content": "Updated"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Comment.objects.get(pk=comment.id).content, "Updated")
        self.client.post(reverse("comment_delete", args=[comment.id]))
        self.assertFalse(Comment.objects.filter(pk=comment.id).exists())

    def test_staff_frontend(self):
        author = User.objects.create_user(
            "comment-author", password="A-strong-password-123"
        )
        staff = User.objects.create_user(
            "comment-staff", password="A-strong-password-123", is_staff=True
        )
        staff.user_permissions.add(Permission.objects.get(codename="delete_comment"))
        comment = Comment.objects.create(
            article=self.article, author=author, content="Original"
        )
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

    def test_article_endpoints(self):
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

    def test_logout_targets(self):
        user = User.objects.create_user(
            "logout-reader", password="A-strong-password-123"
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("comment_logout"),
            {"next": "https://evil.example/collect"},
        )

        self.assertRedirects(response, "/", fetch_redirect_response=False)

    @patch(
        "blog.services.mail.EmailMultiAlternatives.send",
        side_effect=RuntimeError("mail down"),
    )
    def test_failed_registration(self, mock_send):
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
    def test_untrusted_stored(self):
        response = self.client.post(
            reverse("comment_create", args=[self.article.slug]),
            {"nickname": "Guest", "content": "Hello"},
            HTTP_X_FORWARDED_FOR="203.0.113.99",
            REMOTE_ADDR="192.0.2.30",
        )

        self.assertEqual(response.status_code, 200)
        comment_id = response.json()["comment"]["id"]
        self.assertEqual(response.json()["comment"]["ip_address"], "")
        self.assertEqual(Comment.objects.get(pk=comment_id).ip_address, "192.0.2.30")

    def test_registration_username(self):
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
        self.assertFalse(
            User.objects.filter(username="distinctive-reader-name").exists()
        )

    def test_unverified_verification(self):
        User.objects.create_user(
            "pending", password="A-strong-password-123", is_active=False
        )
        response = self.client.post(
            reverse("comment_login"),
            {"username": "pending", "password": "A-strong-password-123"},
        )
        self.assertContains(response, "verification email")

    def test_guest_error(self):
        comment = Comment.objects.create(
            article=self.article, nickname="Guest", content="Hello"
        )
        response = self.client.post(reverse("comment_like", args=[comment.id]))
        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()["ok"])

    def test_comment_site(self):
        response = self.client.get(reverse("comment_assets"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["emoji"], [])

    def test_configured_safely(self):
        pack = CommentEmojiPack.objects.create(config=self.site, name="Basic")
        CommentEmoji.objects.create(
            pack=pack, name="smile", image_url="https://cdn.example/smile.png"
        )
        Comment.objects.create(
            article=self.article, nickname="Guest", content="Hi :smile:"
        )
        response = self.client.get(reverse("comment_list", args=[self.article.slug]))
        self.assertIn(
            "internal-comment-emoji", response.json()["comments"][0]["content_html"]
        )

    def test_comment_order(self):
        first = CommentEmojiPack.objects.create(config=self.site, name="B站")
        CommentEmoji.objects.create(
            pack=first,
            name="bmoji_hot",
            image_url="https://cdn.example/hot.png",
            order=2,
        )
        CommentEmoji.objects.create(
            pack=first,
            name="bmoji_doge",
            image_url="https://cdn.example/doge.png",
            order=1,
        )
        second = CommentEmojiPack.objects.create(config=self.site, name="贴吧", order=1)
        CommentEmoji.objects.create(
            pack=second, name="tieba_1", image_url="https://cdn.example/tieba.png"
        )
        payload = self.client.get(reverse("comment_assets")).json()
        self.assertEqual([pack["name"] for pack in payload["emoji"]], ["B站", "贴吧"])
        self.assertEqual(
            [item["name"] for item in payload["emoji"][0]["items"]],
            ["bmoji_doge", "bmoji_hot"],
        )
        self.assertEqual(payload["emoji"][0]["icon"], "https://cdn.example/doge.png")

    def test_giphy_assets(self):
        CommentGifSource.objects.create(
            config=self.site,
            name="Giphy",
            endpoint="https://api.giphy.com/v1/gifs/search?api_key=secret",
        )
        endpoint = self.client.get(reverse("comment_assets")).json()["gif"][0][
            "endpoint"
        ]
        self.assertIn("/api/comment-gif-proxy/", endpoint)
        self.assertNotIn("secret", endpoint)

    @patch("blog.comment_views.urlopen")
    def test_giphy_results(self, mock_urlopen):
        source = CommentGifSource.objects.create(
            config=self.site,
            name="Giphy",
            endpoint="https://api.giphy.com/v1/gifs/search?api_key=test",
        )

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self):
                return b'{"data":[{"images":{"original":{"url":"https://media.giphy.com/test.gif"}}}]}'

        mock_urlopen.return_value = FakeResponse()
        response = self.client.get(
            reverse("comment_gif_proxy"), {"source": source.pk, "q": "hello"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["results"]), 1)

    @patch("blog.comment_views.urlopen")
    def test_giphy_limit(self, mock_urlopen):
        source = CommentGifSource.objects.create(
            config=self.site,
            name="Giphy",
            endpoint="https://api.giphy.com/v1/gifs/search?api_key=test&limit=999",
        )

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self):
                return b'{"data":[]}'

        mock_urlopen.return_value = FakeResponse()
        response = self.client.get(
            reverse("comment_gif_proxy"), {"source": source.pk, "q": "hello"}
        )
        self.assertEqual(response.status_code, 200)
        request_url = mock_urlopen.call_args.args[0].full_url
        self.assertIn("limit=50", request_url)

    def test_comment_urls(self):
        response = self.client.post(
            reverse("comment_create", args=[self.article.slug]),
            {"nickname": "Guest", "content": "![image](//evil.example/x.png)"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("evil.example", response.json()["comment"]["content_html"])

    def test_comment_scripts(self):
        response = self.client.post(
            reverse("comment_create", args=[self.article.slug]),
            {
                "nickname": "Guest",
                "content": '<font color="Crimson">Important</font><img class="wl-emoji" src="https://cdn.example/love.png"><script>alert(1)</script>',
            },
        )
        self.assertEqual(response.status_code, 200)
        html = response.json()["comment"]["content_html"]
        self.assertIn('<font color="Crimson">Important</font>', html)
        self.assertIn('class="wl-emoji"', html)
        self.assertNotIn("alert(1)", html)

    def test_uploaded_emoji(self):
        response = self.client.post(
            reverse("comment_create", args=[self.article.slug]),
            {
                "nickname": "Guest",
                "content": "![image](/resources/comment-images/example.png)",
            },
        )
        self.assertEqual(response.status_code, 200)
        html = response.json()["comment"]["content_html"]
        self.assertIn('class="internal-comment-image"', html)
        self.assertNotIn('class="wl-emoji"', html)

    def test_registered_verified(self):
        user = User.objects.create_user(
            "verified-reader", password="A-strong-password-123"
        )
        Comment.objects.create(article=self.article, author=user, content="Hello")
        self.client.force_login(user)
        payload = self.client.get(
            reverse("comment_list", args=[self.article.slug])
        ).json()["comments"][0]
        self.assertTrue(payload["verified"])

    def test_staff_sticky(self):
        admin = User.objects.create_user(
            "admin", password="A-strong-password-123", is_staff=True
        )
        admin.user_permissions.add(Permission.objects.get(codename="change_comment"))
        comment = Comment.objects.create(
            article=self.article, nickname="Guest", content="Hello"
        )
        self.client.force_login(admin)
        response = self.client.post(reverse("comment_sticky", args=[comment.id]))
        self.assertEqual(response.status_code, 200)
        comment.refresh_from_db()
        self.assertTrue(comment.is_sticky)

    def test_staff_article(self):
        admin = User.objects.create_user(
            "pin-admin", password="A-strong-password-123", is_staff=True
        )
        admin.user_permissions.add(Permission.objects.get(codename="change_comment"))
        first = Comment.objects.create(
            article=self.article, nickname="First", content="First"
        )
        second = Comment.objects.create(
            article=self.article, nickname="Second", content="Second"
        )
        self.client.force_login(admin)
        self.assertEqual(
            self.client.post(reverse("comment_sticky", args=[first.id])).status_code,
            200,
        )
        response = self.client.post(reverse("comment_sticky", args=[second.id]))
        self.assertEqual(response.status_code, 409)
        self.assertIn("Only one comment can be pinned", response.json()["error"])
        self.assertFalse(Comment.objects.get(pk=second.id).is_sticky)

    def test_comment_exposed(self):
        user = User.objects.create_user(
            "badge-reader", password="A-strong-password-123"
        )
        badge = CommentBadge.objects.create(
            config=self.site, name="Contributor", color="#27ae60"
        )
        CommentBadgeAssignment.objects.create(user=user, badge=badge)
        Comment.objects.create(article=self.article, author=user, content="Hello")
        self.client.force_login(user)
        payload = self.client.get(
            reverse("comment_list", args=[self.article.slug])
        ).json()["comments"][0]
        self.assertEqual(
            payload["badges"], [{"name": "Contributor", "color": "#27ae60"}]
        )

    def test_comment_theme(self):
        user = User.objects.create_user(
            "theme-badge-reader", password="A-strong-password-123"
        )
        badge = CommentBadge.objects.create(
            config=self.site, name="Theme badge", color=""
        )
        CommentBadgeAssignment.objects.create(user=user, badge=badge)
        Comment.objects.create(article=self.article, author=user, content="Hello")
        self.client.force_login(user)
        payload = self.client.get(
            reverse("comment_list", args=[self.article.slug])
        ).json()["comments"][0]
        self.assertEqual(payload["badges"], [{"name": "Theme badge", "color": ""}])

    def test_internal_frontend(self):
        html = render_to_string(
            "components/comments/comment.html",
            {
                "site": self.site,
                "article": self.article,
                "comment_system_configured": True,
            },
        )
        self.assertIn("internal-comments", html)
        self.assertIn("internal.js", html)

    @override_settings(
        AUTHENTICATION_BACKENDS=(
            "django.contrib.auth.backends.ModelBackend",
            "django.contrib.auth.backends.AllowAllUsersModelBackend",
        )
    )
    def test_registration_default(self):
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
