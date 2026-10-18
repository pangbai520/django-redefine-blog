import re
import tempfile
from datetime import timedelta
from io import BytesIO, StringIO
from pathlib import Path

from PIL import Image
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import CommentImage, SiteConfiguration


User = get_user_model()


class LaunchReadinessTests(TestCase):
    def setUp(self):
        cache.clear()
        self.site = SiteConfiguration.objects.create(config_name="Launch", site_name="Launch Blog", is_active=True, comment_system="internal", comment_enabled=True)

    def test_health_endpoint_checks_database_and_disables_caching(self):
        response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertIn("no-cache", response.headers["Cache-Control"])

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_password_reset_completes_without_revealing_unknown_addresses(self):
        user = User.objects.create_user("reader", email="reader@example.com", password="old-password-for-tests")
        known = self.client.post(reverse("password_reset"), {"email": user.email})
        unknown = self.client.post(reverse("password_reset"), {"email": "missing@example.com"})
        self.assertRedirects(known, reverse("password_reset_done"))
        self.assertRedirects(unknown, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        reset_path = re.search(r"https?://[^/]+(/comments/password-reset/[^\s]+)", mail.outbox[0].body).group(1)
        confirm = self.client.get(reset_path, follow=True)
        changed = self.client.post(confirm.redirect_chain[-1][0] if confirm.redirect_chain else reset_path, {"new_password1": "new-password-for-tests", "new_password2": "new-password-for-tests"})
        self.assertRedirects(changed, reverse("password_reset_complete"))
        user.refresh_from_db()
        self.assertTrue(user.check_password("new-password-for-tests"))

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_password_reset_mail_is_rate_limited(self):
        for _ in range(5):
            self.assertEqual(self.client.post(reverse("password_reset"), {"email": "nobody@example.com"}).status_code, 302)
        self.assertEqual(self.client.post(reverse("password_reset"), {"email": "nobody@example.com"}).status_code, 429)

    def test_image_dimensions_are_checked_before_storage(self):
        user = User.objects.create_user("uploader", password="password-for-tests")
        self.client.force_login(user)
        image_bytes = BytesIO()
        Image.new("RGB", (2, 2), "white").save(image_bytes, format="PNG")
        upload = SimpleUploadedFile("large.png", image_bytes.getvalue(), content_type="image/png")
        with override_settings(COMMENT_UPLOAD_MAX_DIMENSION=1):
            response = self.client.post(reverse("comment_upload"), {"image": upload})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(CommentImage.objects.count(), 0)

    def test_orphan_cleanup_supports_dry_run_and_deletion(self):
        user = User.objects.create_user("cleanup", password="password-for-tests")
        with tempfile.TemporaryDirectory(dir=settings.BASE_DIR) as media_root, override_settings(MEDIA_ROOT=media_root):
            upload = CommentImage.objects.create(uploader=user)
            upload.image.save("orphan.png", ContentFile(b"orphan"), save=True)
            CommentImage.objects.filter(pk=upload.pk).update(created_at=timezone.now() - timedelta(days=2))
            output = StringIO()
            call_command("cleanup_orphan_uploads", dry_run=True, stdout=output)
            self.assertTrue(CommentImage.objects.filter(pk=upload.pk).exists())
            with self.captureOnCommitCallbacks(execute=True):
                call_command("cleanup_orphan_uploads", stdout=output)
            self.assertFalse(CommentImage.objects.filter(pk=upload.pk).exists())
            self.assertFalse(Path(media_root, "comment-images", "orphan.png").exists())

    def test_backup_command_creates_a_portable_archive(self):
        with tempfile.TemporaryDirectory(dir=settings.BASE_DIR) as backup_dir:
            call_command("backup_blog", directory=backup_dir, keep=2, stdout=StringIO())
            backups = list(Path(backup_dir).glob("blog-backup-*.zip"))
            self.assertEqual(len(backups), 1)
            self.assertGreater(backups[0].stat().st_size, 0)
