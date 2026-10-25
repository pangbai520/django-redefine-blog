import tempfile
import json
import zipfile
from datetime import timedelta
from io import StringIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.exceptions import ValidationError
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import (
    ArticleModel,
    Comment,
    CommentBadge,
    CommentBadgeAssignment,
    CommentEmojiPack,
    MenuLink,
    SiteConfiguration,
)
from .validators import validate_theme_image


User = get_user_model()


class PublicCoreFeatureTests(TestCase):
    def setUp(self):
        self.site = SiteConfiguration.objects.create(
            config_name="Core",
            site_name="Core Blog",
            site_author="Author",
            is_active=True,
        )

    def test_feed_and_sitemap_only_expose_public_articles(self):
        public = ArticleModel.objects.create(title="Public", content="Visible", is_published=True)
        ArticleModel.objects.create(title="Draft", content="Hidden", is_published=False)
        ArticleModel.objects.create(
            title="Scheduled",
            content="Hidden",
            is_published=True,
            created_at=timezone.now() + timedelta(days=1),
        )

        feed = self.client.get(reverse("article_feed"))
        sitemap = self.client.get(reverse("django.contrib.sitemaps.views.sitemap"))

        self.assertContains(feed, public.title)
        self.assertNotContains(feed, "Draft")
        self.assertNotContains(feed, "Scheduled")
        self.assertContains(sitemap, public.get_absolute_url())
        self.assertNotContains(sitemap, "/article/draft/")
        self.assertNotContains(sitemap, "/article/scheduled/")

    def test_navigation_keeps_articles_with_the_same_publish_time(self):
        published_at = timezone.now() - timedelta(hours=1)
        first = ArticleModel.objects.create(
            title="First", content="One", is_published=True, created_at=published_at
        )
        second = ArticleModel.objects.create(
            title="Second", content="Two", is_published=True, created_at=published_at
        )

        response = self.client.get(second.get_absolute_url())

        self.assertEqual(response.context["prev_article"], first)

    def test_comment_moderation_uses_model_permissions_instead_of_staff_flag(self):
        article = ArticleModel.objects.create(title="Post", content="Body", is_published=True)
        author = User.objects.create_user("author", password="password-for-tests")
        staff_without_permission = User.objects.create_user(
            "staff", password="password-for-tests", is_staff=True
        )
        moderator = User.objects.create_user("moderator", password="password-for-tests")
        moderator.user_permissions.add(
            Permission.objects.get(codename="change_comment"),
            Permission.objects.get(codename="delete_comment"),
        )
        comment = Comment.objects.create(article=article, author=author, content="Hello")

        self.client.force_login(staff_without_permission)
        denied = self.client.post(reverse("comment_sticky", args=[comment.pk]))
        self.assertEqual(denied.status_code, 403)

        self.client.force_login(moderator)
        pinned = self.client.post(reverse("comment_sticky", args=[comment.pk]))
        self.assertEqual(pinned.status_code, 200)
        deleted = self.client.post(reverse("comment_delete", args=[comment.pk]))
        self.assertEqual(deleted.status_code, 200)

    def test_saving_a_sticky_comment_unpins_the_previous_one(self):
        article = ArticleModel.objects.create(title="Post", content="Body", is_published=True)
        first = Comment.objects.create(
            article=article,
            nickname="One",
            content="First",
            is_sticky=True,
        )
        second = Comment.objects.create(
            article=article,
            nickname="Two",
            content="Second",
            is_sticky=True,
        )

        first.refresh_from_db()
        self.assertFalse(first.is_sticky)
        self.assertTrue(second.is_sticky)
        self.assertEqual(Comment.objects.filter(article=article, is_sticky=True).count(), 1)

    def test_comment_reply_cycles_are_rejected(self):
        article = ArticleModel.objects.create(title="Post", content="Body", is_published=True)
        first = Comment.objects.create(article=article, nickname="One", content="First")
        second = Comment.objects.create(
            article=article, nickname="Two", content="Second", parent=first
        )
        first.parent = second
        with self.assertRaisesMessage(ValidationError, "cannot form a cycle"):
            first.full_clean()

    def test_superusers_receive_the_theme_coloured_owner_badge(self):
        badge = CommentBadge.objects.create(
            config=self.site,
            name="博主",
            color="",
            admin_only=True,
        )
        owner = User.objects.create_superuser(
            "owner",
            "owner@example.com",
            "password-for-tests",
        )

        assignment = CommentBadgeAssignment.objects.get(user=owner, badge=badge)
        self.assertEqual(assignment.color_override, "")

    def test_owner_badge_is_backfilled_when_created_after_the_superuser(self):
        owner = User.objects.create_superuser(
            "early-owner",
            "early@example.com",
            "password-for-tests",
        )
        badge = CommentBadge.objects.create(config=self.site, name="博主", color="")

        self.assertTrue(
            CommentBadgeAssignment.objects.filter(user=owner, badge=badge).exists()
        )


class ThemeImageValidationTests(TestCase):
    def test_safe_svg_is_accepted(self):
        upload = SimpleUploadedFile(
            "logo.svg",
            b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><path d="M0 0h1v1z"/></svg>',
            content_type="image/svg+xml",
        )

        validate_theme_image(upload)

    def test_scripted_svg_is_rejected(self):
        upload = SimpleUploadedFile(
            "logo.svg",
            b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
            content_type="image/svg+xml",
        )

        with self.assertRaises(ValidationError):
            validate_theme_image(upload)


class DemoContentTests(TransactionTestCase):
    reset_sequences = True

    def test_create_demo_requires_a_superuser(self):
        SiteConfiguration.objects.all().delete()

        with self.assertRaisesMessage(
            CommandError,
            "python manage.py createsuperuser",
        ):
            call_command("create_demo", stdout=StringIO())

        self.assertFalse(SiteConfiguration.objects.exists())
        self.assertFalse(ArticleModel.objects.exists())

    def test_create_demo_command_creates_the_public_demo(self):
        SiteConfiguration.objects.all().delete()
        User.objects.create_superuser(
            username="owner",
            email="owner@example.com",
            password="not-a-demo-password",
        )
        output = StringIO()
        call_command("create_demo", stdout=output)

        site = SiteConfiguration.objects.get(is_active=True)
        self.assertIn("Demo site created.", output.getvalue())
        self.assertEqual(site.site_name, "Django Redefine")
        self.assertEqual(User.objects.get(username="owner").profile.display_name, "The Redefine Team")
        self.assertFalse(site.site_avatar)
        self.assertFalse(site.site_logo)
        article = ArticleModel.objects.get(slug="hello-world")
        self.assertEqual(
            timezone.localtime(article.created_at).strftime("%Y-%m-%d %H:%M:%S"),
            "1900-01-01 00:00:00",
        )
        self.assertEqual(
            list(article.category.values_list("slug", flat=True)),
            ["run"],
        )
        self.assertEqual(article.category.get().parent.slug, "start")
        self.assertEqual(
            set(article.tags.values_list("slug", flat=True)),
            {
                "demo",
                "first-post",
                "hello-world",
                "django",
                "django-blog",
                "django-redefine",
            },
        )
        self.assertTrue(MenuLink.objects.filter(config=site, name="Home").exists())
        self.assertTrue(MenuLink.objects.filter(config=site, name="Admin").exists())
        badge = CommentBadge.objects.get(config=site, name="博主")
        self.assertEqual(badge.color, "")
        self.assertTrue(CommentBadgeAssignment.objects.filter(user__username="owner").exists())
        self.assertEqual(
            list(CommentEmojiPack.objects.filter(config=site).values_list("name", flat=True)),
            ["bilibili"],
        )

    def test_create_demo_command_does_not_replace_an_existing_site(self):
        SiteConfiguration.objects.all().delete()
        User.objects.create_superuser(
            username="owner",
            email="owner@example.com",
            password="not-a-demo-password",
        )
        SiteConfiguration.objects.create(
            config_name="Existing",
            site_name="Existing Blog",
            is_active=True,
        )
        output = StringIO()

        call_command("create_demo", stdout=output)

        self.assertEqual(SiteConfiguration.objects.count(), 1)
        self.assertEqual(SiteConfiguration.objects.get().site_name, "Existing Blog")
        self.assertFalse(ArticleModel.objects.exists())
        self.assertIn("nothing changed", output.getvalue())


class PortableDataTests(TransactionTestCase):
    reset_sequences = True

    def test_export_and_replace_import_restore_database_and_media(self):
        with tempfile.TemporaryDirectory(dir=settings.BASE_DIR) as temporary:
            with override_settings(MEDIA_ROOT=temporary):
                site = SiteConfiguration.objects.create(
                    config_name="Portable", site_name="Portable Blog", is_active=True
                )
                site.site_avatar.save(
                    "avatar.svg",
                    ContentFile(b'<svg xmlns="http://www.w3.org/2000/svg"/>'),
                    save=True,
                )
                article = ArticleModel.objects.create(
                    title="Portable post", content="Body", is_published=True
                )
                archive = Path(temporary) / "blog-export.zip"

                call_command("export_blog", str(archive), stdout=StringIO())
                # overwriting an archive below MEDIA_ROOT must not embed the
                # previous ZIP as another media file
                call_command("export_blog", str(archive), stdout=StringIO())
                with zipfile.ZipFile(archive) as exported:
                    manifest = json.loads(exported.read("manifest.json"))
                self.assertEqual(manifest["media_files"], 1)
                article.delete()

                with self.assertRaises(CommandError):
                    call_command("import_blog", str(archive), stdout=StringIO())

                call_command("import_blog", str(archive), replace=True, stdout=StringIO())

                restored = ArticleModel.objects.get(title="Portable post")
                restored_site = SiteConfiguration.objects.get(config_name="Portable")
                self.assertEqual(restored.content, "Body")
                self.assertEqual(
                    Path(restored_site.site_avatar.path).read_bytes(),
                    b'<svg xmlns="http://www.w3.org/2000/svg"/>',
                )
