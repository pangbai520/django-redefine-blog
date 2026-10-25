import re
import tempfile
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from PIL import Image
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .cache_utils import cache_version
from .models import ArticleModel, Comment, SiteConfiguration, UserProfile


User = get_user_model()


def avatar_upload(name="avatar.png", size=(32, 32), image_format="PNG"):
    payload = BytesIO()
    Image.new("RGB", size, "#a31f34").save(payload, format=image_format)
    return SimpleUploadedFile(name, payload.getvalue(), content_type="image/png")


class UserProfileTests(TestCase):
    password = "profile-password-for-tests"

    def setUp(self):
        cache.clear()
        self.site = SiteConfiguration.objects.create(
            config_name="Profile tests",
            site_name="Profile Blog",
            is_active=True,
            comment_enabled=True,
            comment_system="internal",
        )
        self.user = User.objects.create_user(
            "reader",
            email="reader@example.com",
            password=self.password,
        )

    def test_profile_is_created_with_the_user(self):
        self.assertTrue(UserProfile.objects.filter(user=self.user).exists())
        self.assertEqual(self.user.profile.resolved_display_name, "reader")

    def test_profile_page_requires_sign_in(self):
        response = self.client.get(reverse("comment_profile"))

        self.assertRedirects(
            response,
            f"{reverse('comment_login')}?next={reverse('comment_profile')}",
            fetch_redirect_response=False,
        )

    def test_display_name_is_used_by_existing_comments(self):
        article = ArticleModel.objects.create(
            title="Profile comment",
            slug="profile-comment",
            content="Content",
            is_published=True,
        )
        Comment.objects.create(article=article, author=self.user, content="Hello")
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("comment_profile"),
            {
                "action": "profile",
                "display_name": "Redefine Reader",
            },
        )

        self.assertRedirects(response, reverse("comment_profile") + "?updated=1")
        payload = self.client.get(reverse("comment_list", args=[article.slug])).json()
        self.assertEqual(payload["comments"][0]["author"], "Redefine Reader")

    def test_avatar_is_validated_and_exposed_to_comments(self):
        article = ArticleModel.objects.create(
            title="Avatar comment",
            slug="avatar-comment",
            content="Content",
            is_published=True,
        )
        Comment.objects.create(article=article, author=self.user, content="Hello")
        self.client.force_login(self.user)

        with tempfile.TemporaryDirectory(dir=settings.BASE_DIR) as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(
                reverse("comment_profile"),
                {
                    "action": "profile",
                    "display_name": "",
                    "avatar": avatar_upload(),
                },
            )
            self.assertRedirects(response, reverse("comment_profile") + "?updated=1")
            self.user.profile.refresh_from_db()
            self.assertTrue(Path(self.user.profile.avatar.path).exists())

            payload = self.client.get(reverse("comment_list", args=[article.slug])).json()
            self.assertIn("/user-avatars/", payload["comments"][0]["avatar"])

    def test_avatar_crop_is_applied_on_the_server(self):
        self.client.force_login(self.user)

        with tempfile.TemporaryDirectory(dir=settings.BASE_DIR) as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(
                reverse("comment_profile"),
                {
                    "action": "profile",
                    "display_name": "",
                    "avatar": avatar_upload(size=(80, 40)),
                    "avatar_crop_x": "20",
                    "avatar_crop_y": "0",
                    "avatar_crop_size": "40",
                },
            )

            self.assertRedirects(response, reverse("comment_profile") + "?updated=1")
            self.user.profile.refresh_from_db()
            with Image.open(self.user.profile.avatar.path) as cropped:
                self.assertEqual(cropped.size, (512, 512))
                self.assertEqual(cropped.format, "WEBP")

    def test_avatar_crop_preserves_transparency(self):
        payload = BytesIO()
        transparent = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        transparent.paste((255, 255, 255, 255), (8, 8, 24, 24))
        transparent.save(payload, format="PNG")
        upload = SimpleUploadedFile(
            "transparent.png",
            payload.getvalue(),
            content_type="image/png",
        )
        self.client.force_login(self.user)

        with tempfile.TemporaryDirectory(dir=settings.BASE_DIR) as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(
                reverse("comment_profile"),
                {
                    "action": "profile",
                    "display_name": "",
                    "avatar": upload,
                    "avatar_crop_x": "0",
                    "avatar_crop_y": "0",
                    "avatar_crop_size": "32",
                },
            )
            self.assertRedirects(response, reverse("comment_profile") + "?updated=1")
            self.user.profile.refresh_from_db()
            with Image.open(self.user.profile.avatar.path) as cropped:
                self.assertIn("A", cropped.getbands())
                self.assertEqual(cropped.getpixel((0, 0))[3], 0)

    def test_invalid_avatar_bytes_are_rejected(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("comment_profile"),
            {
                "action": "profile",
                "display_name": "",
                "avatar": SimpleUploadedFile(
                    "avatar.png",
                    b"not an image",
                    content_type="image/png",
                ),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Upload a valid image.")
        self.user.profile.refresh_from_db()
        self.assertFalse(self.user.profile.avatar)

    def test_avatar_dimensions_are_bounded(self):
        self.client.force_login(self.user)

        with override_settings(PROFILE_AVATAR_MAX_DIMENSION=16):
            response = self.client.post(
                reverse("comment_profile"),
                {
                    "action": "profile",
                    "display_name": "",
                    "avatar": avatar_upload(size=(32, 32)),
                },
            )

        self.assertContains(response, "Avatar dimensions are too large.")
        self.user.profile.refresh_from_db()
        self.assertFalse(self.user.profile.avatar)

    def test_current_avatar_can_be_removed(self):
        self.client.force_login(self.user)

        with tempfile.TemporaryDirectory(dir=settings.BASE_DIR) as media_root, override_settings(MEDIA_ROOT=media_root):
            self.user.profile.avatar = avatar_upload()
            self.user.profile.save(update_fields=("avatar",))
            avatar_path = Path(self.user.profile.avatar.path)
            self.assertTrue(avatar_path.exists())

            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    reverse("comment_profile"),
                    {
                        "action": "profile",
                        "display_name": "",
                        "remove_avatar": "on",
                    },
                )

            self.assertRedirects(response, reverse("comment_profile") + "?updated=1")
            self.user.profile.refresh_from_db()
            self.assertFalse(self.user.profile.avatar)
            self.assertFalse(avatar_path.exists())

    def test_profile_review_keeps_the_public_identity_until_approval(self):
        article = ArticleModel.objects.create(
            title="Profile moderation",
            slug="profile-moderation",
            content="Content",
            is_published=True,
        )
        Comment.objects.create(article=article, author=self.user, content="Hello")
        self.user.profile.display_name = "Current name"
        self.user.profile.save(update_fields=("display_name",))
        self.site.comment_profile_review_enabled = True
        self.site.save(update_fields=("comment_profile_review_enabled",))
        self.assertTrue(SiteConfiguration.get_config().comment_profile_review_enabled)
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("comment_profile"),
            {"action": "profile", "display_name": "Pending name"},
        )

        self.assertRedirects(response, reverse("comment_profile") + "?review=pending")
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.display_name, "Current name")
        self.assertEqual(self.user.profile.pending_display_name, "Pending name")
        self.assertTrue(self.user.profile.profile_review_pending)
        payload = self.client.get(reverse("comment_list", args=[article.slug])).json()
        self.assertEqual(payload["comments"][0]["author"], "Current name")

        self.assertTrue(self.user.profile.approve_pending_profile_changes())
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.display_name, "Pending name")
        self.assertFalse(self.user.profile.profile_review_pending)

    def test_profile_review_can_reject_a_pending_avatar_without_touching_the_live_one(self):
        self.site.comment_profile_review_enabled = True
        self.site.save(update_fields=("comment_profile_review_enabled",))
        self.client.force_login(self.user)

        with tempfile.TemporaryDirectory(dir=settings.BASE_DIR) as media_root, override_settings(MEDIA_ROOT=media_root):
            self.user.profile.avatar = avatar_upload("current.png")
            self.user.profile.save(update_fields=("avatar",))
            current_name = self.user.profile.avatar.name
            response = self.client.post(
                reverse("comment_profile"),
                {
                    "action": "profile",
                    "display_name": "reader",
                    "avatar": avatar_upload("pending.png"),
                },
            )
            self.assertRedirects(response, reverse("comment_profile") + "?review=pending")
            self.user.profile.refresh_from_db()
            self.assertEqual(self.user.profile.avatar.name, current_name)
            self.assertTrue(self.user.profile.pending_avatar)

            with self.captureOnCommitCallbacks(execute=True):
                self.user.profile.clear_pending_profile_changes()
            self.user.profile.refresh_from_db()
            self.assertEqual(self.user.profile.avatar.name, current_name)
            self.assertFalse(self.user.profile.pending_avatar)
            self.assertFalse(self.user.profile.profile_review_pending)

    def test_approved_pending_avatar_is_copied_to_the_live_profile(self):
        self.site.comment_profile_review_enabled = True
        self.site.save(update_fields=("comment_profile_review_enabled",))
        self.client.force_login(self.user)

        with tempfile.TemporaryDirectory(dir=settings.BASE_DIR) as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(
                reverse("comment_profile"),
                {
                    "action": "profile",
                    "display_name": "Reviewed reader",
                    "avatar": avatar_upload("reviewed.png"),
                },
            )
            self.assertRedirects(response, reverse("comment_profile") + "?review=pending")
            self.user.profile.refresh_from_db()
            pending_path = Path(self.user.profile.pending_avatar.path)
            self.assertTrue(pending_path.exists())

            with self.captureOnCommitCallbacks(execute=True):
                self.assertTrue(self.user.profile.approve_pending_profile_changes())
            self.user.profile.refresh_from_db()
            self.assertEqual(self.user.profile.display_name, "Reviewed reader")
            self.assertTrue(Path(self.user.profile.avatar.path).exists())
            self.assertNotEqual(Path(self.user.profile.avatar.path), pending_path)
            self.assertFalse(pending_path.exists())

    def test_staff_profile_changes_bypass_review(self):
        self.site.comment_profile_review_enabled = True
        self.site.save(update_fields=("comment_profile_review_enabled",))
        self.user.is_staff = True
        self.user.save(update_fields=("is_staff",))
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("comment_profile"),
            {"action": "profile", "display_name": "Staff name"},
        )

        self.assertRedirects(response, reverse("comment_profile") + "?updated=1")
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.display_name, "Staff name")
        self.assertFalse(self.user.profile.profile_review_pending)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_email_change_keeps_old_address_until_confirmation(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("comment_profile"),
            {
                "action": "email",
                "email": "new-reader@example.com",
                "current_password": self.password,
            },
        )

        self.assertRedirects(response, reverse("comment_profile") + "?email=pending")
        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.email, "reader@example.com")
        self.assertEqual(self.user.profile.pending_email, "new-reader@example.com")
        self.assertEqual(len(mail.outbox), 1)

        confirm_path = re.search(
            r"https?://[^/]+(/comments/profile/email/[^\s]+/)",
            mail.outbox[0].body,
        ).group(1)
        confirmation = self.client.get(confirm_path)

        self.assertEqual(confirmation.status_code, 200)
        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.email, "new-reader@example.com")
        self.assertEqual(self.user.profile.pending_email, "")

    def test_email_change_requires_current_password(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("comment_profile"),
            {
                "action": "email",
                "email": "new-reader@example.com",
                "current_password": "wrong-password",
            },
        )

        self.assertContains(
            response,
            "Enter your current password to change your email address.",
        )
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.pending_email, "")

    @patch(
        "blog.comment_views.EmailMultiAlternatives.send",
        side_effect=ValueError("Invalid sender address"),
    )
    def test_email_delivery_failure_returns_a_form_error(self, send):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("comment_profile"),
            {
                "action": "email",
                "email": "new-reader@example.com",
                "current_password": self.password,
            },
        )

        self.assertEqual(response.status_code, 502)
        self.assertContains(
            response,
            "We could not send the confirmation email. Your email address was not changed.",
            status_code=502,
        )
        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.email, "reader@example.com")
        self.assertEqual(self.user.profile.pending_email, "")
        send.assert_called_once()

    def test_email_change_rejects_an_address_used_by_another_account(self):
        User.objects.create_user("other", email="other@example.com", password=self.password)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("comment_profile"),
            {
                "action": "email",
                "email": "other@example.com",
                "current_password": self.password,
            },
        )

        self.assertContains(response, "This email address is already registered.")

    @patch("blog.comment_views._send_profile_email_confirmation")
    def test_profile_save_never_submits_email_fields(self, send_confirmation):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("comment_profile"),
            {
                "action": "profile",
                "display_name": "Avatar only",
                "email": "browser-autofill@example.com",
                "current_password": self.password,
            },
        )

        self.assertRedirects(response, reverse("comment_profile") + "?updated=1")
        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.email, "reader@example.com")
        self.assertEqual(self.user.profile.pending_email, "")
        self.assertEqual(self.user.profile.display_name, "Avatar only")
        send_confirmation.assert_not_called()

    def test_superuser_profile_drives_the_default_blog_author(self):
        owner = User.objects.create_superuser(
            "owner",
            email="owner@example.com",
            password=self.password,
        )
        article = ArticleModel.objects.create(
            title="Owner article",
            slug="owner-article",
            content="Content",
            is_published=True,
        )

        with tempfile.TemporaryDirectory(
            dir=settings.BASE_DIR
        ) as media_root, override_settings(MEDIA_ROOT=media_root):
            owner.profile.display_name = "Blog Owner"
            owner.profile.avatar = avatar_upload("owner.png")
            owner.profile.save(update_fields=("display_name", "avatar"))

            response = self.client.get(reverse("article", args=[article.slug]))

            self.assertContains(response, "Blog Owner")
            self.assertContains(response, owner.profile.avatar.url)

    def test_owner_profile_invalidates_public_content_and_license_author(self):
        owner = User.objects.create_superuser(
            "license-owner",
            email="owner@example.com",
            password=self.password,
        )
        article = ArticleModel.objects.create(
            title="Reserved article",
            slug="reserved-article",
            content="Content",
            is_published=True,
        )
        self.site.copyright_type = "all_rights_reserved"
        self.site.save(update_fields=("copyright_type",))
        before = cache_version("content")

        owner.profile.display_name = "Named Blog Owner"
        owner.profile.save(update_fields=("display_name",))

        self.assertGreater(cache_version("content"), before)
        self.assertIn("Named Blog Owner", str(article.licence_label))

    def test_article_author_override_still_wins_over_the_owner_profile(self):
        owner = User.objects.create_superuser(
            "owner",
            email="owner@example.com",
            password=self.password,
        )
        owner.profile.display_name = "Blog Owner"
        owner.profile.save(update_fields=("display_name",))
        article = ArticleModel.objects.create(
            title="Guest article",
            slug="guest-article",
            writer="Guest Writer",
            content="Content",
            is_published=True,
        )

        response = self.client.get(reverse("article", args=[article.slug]))

        self.assertContains(response, "Guest Writer")
        self.assertContains(response, "Blog Owner")

    def test_invalid_email_confirmation_link_is_rejected(self):
        response = self.client.get(
            reverse("comment_profile_email_confirm", args=["not-a-valid-token"])
        )

        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "reader@example.com")

    def test_profile_page_contains_password_change_form(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("comment_profile"))

        self.assertContains(response, 'class="page-title-header profile-heading-title"')
        self.assertNotContains(response, "fa-solid fa-user-pen")
        self.assertContains(response, 'name="action" value="password"')
        self.assertContains(response, "Change password")
        self.assertContains(response, "Username cannot be changed.")

    def test_password_change_stays_in_profile_and_preserves_the_session(self):
        self.client.force_login(self.user)
        return_to = "/article/source-article/#comments"
        new_password = "new-profile-password-for-tests"

        response = self.client.post(
            reverse("comment_profile"),
            {
                "action": "password",
                "next": return_to,
                "old_password": self.password,
                "new_password1": new_password,
                "new_password2": new_password,
            },
        )

        parsed = urlparse(response.url)
        self.assertEqual(parsed.path, reverse("comment_profile"))
        self.assertEqual(parse_qs(parsed.query)["password"], ["updated"])
        self.assertEqual(parse_qs(parsed.query)["next"], [return_to])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new_password))
        follow_up = self.client.get(response.url)
        self.assertTrue(follow_up.wsgi_request.user.is_authenticated)
        self.assertContains(follow_up, "Password updated")

    def test_oauth_style_account_can_set_its_first_password(self):
        self.user.set_unusable_password()
        self.user.save(update_fields=("password",))
        self.client.force_login(self.user)
        new_password = "first-local-password-for-tests"

        page = self.client.get(reverse("comment_profile"))
        response = self.client.post(
            reverse("comment_profile"),
            {
                "action": "password",
                "new_password1": new_password,
                "new_password2": new_password,
            },
        )

        self.assertContains(page, "Set password")
        self.assertNotContains(page, 'class="profile-form profile-email-form"')
        self.assertRedirects(response, reverse("comment_profile") + "?password=updated")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new_password))
        self.assertTrue(self.client.get(reverse("comment_profile")).wsgi_request.user.is_authenticated)

    def test_oauth_style_account_cannot_change_email_without_a_password(self):
        self.user.set_unusable_password()
        self.user.save(update_fields=("password",))
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("comment_profile"),
            {"action": "email", "email": "new-reader@example.com"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(
            response,
            "Set a password before changing your email address.",
            status_code=400,
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "reader@example.com")

    def test_profile_back_button_returns_to_the_source_comment_section(self):
        self.client.force_login(self.user)
        return_to = "/article/source-article/#comments"

        response = self.client.get(
            reverse("comment_profile"),
            {"next": return_to},
        )

        self.assertContains(response, f'href="{return_to}"')
        self.assertContains(response, 'name="next" value="/article/source-article/#comments"', count=3)

    def test_profile_rejects_an_external_return_url(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("comment_profile"),
            {"next": "https://example.net/phishing"},
        )

        self.assertContains(response, 'href="/"')

    def test_comment_profile_link_targets_the_same_article_comments(self):
        article = ArticleModel.objects.create(
            title="Profile return",
            slug="profile-return",
            content="Content",
            is_published=True,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("article", args=[article.slug]))

        self.assertContains(response, 'id="comments"')
        self.assertContains(
            response,
            f'{reverse("comment_profile")}?next=/article/{article.slug}/%23comments',
        )
        self.assertNotContains(response, f'href="{reverse("password_change")}"')

    def test_legacy_password_change_url_redirects_to_profile_section(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("password_change"),
            {"next": "/article/source-article/#comments"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("comment_profile") + "?"))
        self.assertTrue(response.url.endswith("#profile-password"))

    def test_profile_page_is_translated(self):
        self.client.force_login(self.user)
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "zh-hans"

        response = self.client.get(reverse("comment_profile"))

        self.assertContains(response, "编辑个人资料")
        self.assertContains(response, "用户名不能修改。")
        self.assertContains(response, "裁剪头像")
        self.assertNotContains(response, "点击头像即可选择并裁剪新图片。")
        self.assertContains(response, 'class="page-title-header profile-heading-title"')
