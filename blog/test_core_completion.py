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
from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import ArticleModel, Comment, SiteConfiguration


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

    def test_database_allows_only_one_sticky_comment_per_article(self):
        article = ArticleModel.objects.create(title="Post", content="Body", is_published=True)
        Comment.objects.create(article=article, nickname="One", content="First", is_sticky=True)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Comment.objects.create(article=article, nickname="Two", content="Second", is_sticky=True)

    def test_comment_reply_cycles_are_rejected(self):
        article = ArticleModel.objects.create(title="Post", content="Body", is_published=True)
        first = Comment.objects.create(article=article, nickname="One", content="First")
        second = Comment.objects.create(
            article=article, nickname="Two", content="Second", parent=first
        )
        first.parent = second
        with self.assertRaisesMessage(ValidationError, "cannot form a cycle"):
            first.full_clean()


class PortableDataTests(TransactionTestCase):
    reset_sequences = True

    def test_export_and_replace_import_restore_database_and_media(self):
        with tempfile.TemporaryDirectory(dir=settings.BASE_DIR) as temporary:
            with override_settings(MEDIA_ROOT=temporary):
                site = SiteConfiguration.objects.create(
                    config_name="Portable", site_name="Portable Blog", is_active=True
                )
                site.site_avatar.save("avatar.txt", ContentFile(b"portable-media"), save=True)
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
                self.assertEqual(Path(restored_site.site_avatar.path).read_bytes(), b"portable-media")
