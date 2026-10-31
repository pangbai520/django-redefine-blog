import tempfile
from io import BytesIO
from pathlib import Path

from PIL import Image
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse


User = get_user_model()


def valid_png():
    payload = BytesIO()
    Image.new("RGB", (8, 8), "#a31f34").save(payload, format="PNG")
    return SimpleUploadedFile("article.png", payload.getvalue(), content_type="image/png")


class EditorUploadSecurityTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)

    def _csrf_token(self):
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        return self.client.cookies[settings.CSRF_COOKIE_NAME].value

    def test_anonymous_upload_is_rejected_without_creating_a_file(self):
        with tempfile.TemporaryDirectory(dir=settings.BASE_DIR) as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(
                reverse("mdeditor_upload"),
                {"editormd-image-file": valid_png()},
            )

        self.assertEqual(response.status_code, 403)

    def test_staff_without_article_permission_is_rejected(self):
        user = User.objects.create_user(
            "limited-staff",
            password="A-strong-password-123",
            is_staff=True,
        )
        self.client.force_login(user)
        token = self._csrf_token()

        response = self.client.post(
            reverse("mdeditor_upload"),
            {"editormd-image-file": valid_png()},
            HTTP_X_CSRFTOKEN=token,
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["success"], 0)

    def test_superuser_can_upload_a_verified_image(self):
        user = User.objects.create_superuser(
            "editor-owner",
            email="owner@example.com",
            password="A-strong-password-123",
        )
        self.client.force_login(user)
        token = self._csrf_token()

        with tempfile.TemporaryDirectory(dir=settings.BASE_DIR) as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(
                reverse("mdeditor_upload"),
                {"editormd-image-file": valid_png()},
                HTTP_X_CSRFTOKEN=token,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["success"], 1)
        self.assertTrue(response.json()["url"].endswith(".png"))
        self.assertEqual(response.headers["X-Frame-Options"], "SAMEORIGIN")

    def test_fake_image_bytes_are_rejected(self):
        user = User.objects.create_superuser(
            "editor-owner",
            email="owner@example.com",
            password="A-strong-password-123",
        )
        self.client.force_login(user)
        token = self._csrf_token()

        response = self.client.post(
            reverse("mdeditor_upload"),
            {
                "editormd-image-file": SimpleUploadedFile(
                    "fake.png",
                    b"not-an-image",
                    content_type="image/png",
                )
            },
            HTTP_X_CSRFTOKEN=token,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["success"], 0)

    def test_identical_article_images_reuse_the_same_file(self):
        user = User.objects.create_superuser(
            "dedupe-editor",
            email="editor@example.com",
            password="A-strong-password-123",
        )
        self.client.force_login(user)
        token = self._csrf_token()

        with tempfile.TemporaryDirectory(dir=settings.BASE_DIR) as media_root, override_settings(MEDIA_ROOT=media_root):
            first = self.client.post(
                reverse("mdeditor_upload"),
                {"editormd-image-file": valid_png()},
                HTTP_X_CSRFTOKEN=token,
            )
            second = self.client.post(
                reverse("mdeditor_upload"),
                {"editormd-image-file": valid_png()},
                HTTP_X_CSRFTOKEN=token,
            )

            self.assertEqual(first.json()["url"], second.json()["url"])
            self.assertEqual(len(list(Path(media_root, "editor").glob("*.png"))), 1)
