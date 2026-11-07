import importlib
import tempfile
import uuid
from datetime import timedelta
from io import BytesIO
from pathlib import Path

from PIL import Image
from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from blog.models import ArticleModel, EditorImage, EditorImageLease, EditorImageRef

User = get_user_model()


def valid_png():
    payload = BytesIO()
    Image.new("RGB", (8, 8), "#a31f34").save(payload, format="PNG")
    return SimpleUploadedFile(
        "article.png", payload.getvalue(), content_type="image/png"
    )


class EditorUploadSecurityTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)

    def _csrf_token(self):
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        return self.client.cookies[settings.CSRF_COOKIE_NAME].value

    def test_anonymous_file(self):
        with tempfile.TemporaryDirectory(
            dir=settings.BASE_DIR
        ) as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(
                reverse("mdeditor_upload"),
                {"editormd-image-file": valid_png()},
            )

        self.assertEqual(response.status_code, 403)

    def test_staff_rejected(self):
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

    def test_superuser_image(self):
        user = User.objects.create_superuser(
            "editor-owner",
            email="owner@example.com",
            password="A-strong-password-123",
        )
        self.client.force_login(user)
        token = self._csrf_token()

        with tempfile.TemporaryDirectory(
            dir=settings.BASE_DIR
        ) as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(
                reverse("mdeditor_upload"),
                {"editormd-image-file": valid_png()},
                HTTP_X_CSRFTOKEN=token,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["success"], 1)
        self.assertIn("/content-images/", response.json()["url"])
        self.assertTrue(response.json()["url"].endswith(".png"))
        self.assertTrue(response.json()["id"])
        self.assertEqual(EditorImage.objects.count(), 1)
        self.assertEqual(response.headers["X-Frame-Options"], "SAMEORIGIN")

    def test_fake_rejected(self):
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

    def test_identical_file(self):
        user = User.objects.create_superuser(
            "dedupe-editor",
            email="editor@example.com",
            password="A-strong-password-123",
        )
        self.client.force_login(user)
        token = self._csrf_token()

        with tempfile.TemporaryDirectory(
            dir=settings.BASE_DIR
        ) as media_root, override_settings(MEDIA_ROOT=media_root):
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
            self.assertEqual(
                len(list(Path(media_root, "content-images").glob("*.png"))), 1
            )
            self.assertEqual(EditorImage.objects.count(), 1)

    def test_draft_cleanup(self):
        user = User.objects.create_superuser(
            "draft-editor",
            email="draft@example.com",
            password="A-strong-password-123",
        )
        self.client.force_login(user)
        token = self._csrf_token()
        first_draft = uuid.uuid4()
        second_draft = uuid.uuid4()

        with tempfile.TemporaryDirectory(
            dir=settings.BASE_DIR
        ) as media_root, override_settings(MEDIA_ROOT=media_root):
            for draft_id in (first_draft, second_draft):
                response = self.client.post(
                    reverse("mdeditor_upload"),
                    {
                        "editormd-image-file": valid_png(),
                        "draft_id": str(draft_id),
                    },
                    HTTP_X_CSRFTOKEN=token,
                )
                self.assertEqual(response.status_code, 200)

            image = EditorImage.objects.get()
            self.assertEqual(EditorImageLease.objects.filter(image=image).count(), 2)
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(
                    reverse("mdeditor_image_abandon"),
                    {"draft_id": str(first_draft)},
                    HTTP_X_CSRFTOKEN=token,
                )
            self.assertTrue(EditorImage.objects.filter(pk=image.pk).exists())

            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    reverse("mdeditor_image_abandon"),
                    {"draft_id": str(second_draft)},
                    HTTP_X_CSRFTOKEN=token,
                )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["deleted"], 1)
            self.assertFalse(EditorImage.objects.filter(pk=image.pk).exists())
            self.assertFalse(Path(media_root, image.image.name).exists())

    def test_saved_image(self):
        user = User.objects.create_superuser(
            "saved-draft-editor",
            email="saved-draft@example.com",
            password="A-strong-password-123",
        )
        self.client.force_login(user)
        token = self._csrf_token()
        draft_id = uuid.uuid4()

        with tempfile.TemporaryDirectory(
            dir=settings.BASE_DIR
        ) as media_root, override_settings(MEDIA_ROOT=media_root):
            uploaded = self.client.post(
                reverse("mdeditor_upload"),
                {
                    "editormd-image-file": valid_png(),
                    "draft_id": str(draft_id),
                },
                HTTP_X_CSRFTOKEN=token,
            )
            image = EditorImage.objects.get()
            ArticleModel.objects.create(
                title="Saved article image",
                content=f"![Saved]({uploaded.json()['url']})",
            )
            response = self.client.post(
                reverse("mdeditor_image_abandon"),
                {"draft_id": str(draft_id)},
                HTTP_X_CSRFTOKEN=token,
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["deleted"], 0)
            self.assertTrue(EditorImage.objects.filter(pk=image.pk).exists())
            self.assertFalse(EditorImageLease.objects.filter(image=image).exists())

    def test_library_reuse(self):
        user = User.objects.create_superuser(
            "library-editor",
            email="library@example.com",
            password="A-strong-password-123",
        )
        self.client.force_login(user)
        token = self._csrf_token()

        with tempfile.TemporaryDirectory(
            dir=settings.BASE_DIR
        ) as media_root, override_settings(MEDIA_ROOT=media_root):
            uploaded = self.client.post(
                reverse("mdeditor_upload"),
                {"editormd-image-file": valid_png()},
                HTTP_X_CSRFTOKEN=token,
            )
            image_url = uploaded.json()["url"]
            image = EditorImage.objects.get()
            article = ArticleModel.objects.create(
                title="Image reference",
                content=f"![Article image]({image_url})",
            )
            self.assertTrue(
                EditorImageRef.objects.filter(
                    image=image,
                    target_type=EditorImageRef.ARTICLE,
                    target_id=article.pk,
                ).exists()
            )

            library = self.client.get(reverse("mdeditor_image_list"))
            self.assertEqual(library.status_code, 200)
            self.assertEqual(library.json()["images"][0]["ref_count"], 1)
            blocked = self.client.post(
                reverse("mdeditor_image_delete", args=(image.pk,)),
                HTTP_X_CSRFTOKEN=token,
            )
            self.assertEqual(blocked.status_code, 409)

            article.content = "No image"
            article.save(update_fields=("content",))
            self.assertFalse(EditorImageRef.objects.filter(image=image).exists())
            with self.captureOnCommitCallbacks(execute=True):
                deleted = self.client.post(
                    reverse("mdeditor_image_delete", args=(image.pk,)),
                    HTTP_X_CSRFTOKEN=token,
                )
            self.assertEqual(deleted.status_code, 200)
            self.assertFalse(EditorImage.objects.filter(pk=image.pk).exists())
            self.assertFalse(Path(media_root, image.image.name).exists())

    def test_orphan_cleanup(self):
        user = User.objects.create_superuser(
            "cleanup-editor",
            email="cleanup@example.com",
            password="A-strong-password-123",
        )
        self.client.force_login(user)
        token = self._csrf_token()

        with tempfile.TemporaryDirectory(
            dir=settings.BASE_DIR
        ) as media_root, override_settings(MEDIA_ROOT=media_root):
            draft_id = uuid.uuid4()
            self.client.post(
                reverse("mdeditor_upload"),
                {
                    "editormd-image-file": valid_png(),
                    "draft_id": str(draft_id),
                },
                HTTP_X_CSRFTOKEN=token,
            )
            image = EditorImage.objects.get()
            path = Path(media_root, image.image.name)
            EditorImage.objects.filter(pk=image.pk).update(
                created_at=timezone.now() - timedelta(days=2)
            )
            EditorImageLease.objects.filter(image=image).update(
                created_at=timezone.now() - timedelta(days=2)
            )
            with self.captureOnCommitCallbacks(execute=True):
                call_command("cleanup_orphan_uploads")
            self.assertFalse(EditorImage.objects.filter(pk=image.pk).exists())
            self.assertFalse(path.exists())

    def test_library_permission(self):
        user = User.objects.create_user(
            "library-reader",
            password="A-strong-password-123",
            is_staff=True,
        )
        self.client.force_login(user)
        self.assertEqual(
            self.client.get(reverse("mdeditor_image_list")).status_code,
            403,
        )


class ContentImageMigrationTests(TestCase):
    def test_path_migration(self):
        migration = importlib.import_module(
            "blog.migrations.0013_content_image_paths"
        )
        digest = "a" * 64
        old_name = f"editor/{digest}.png"
        new_name = f"content-images/{digest}.png"

        with tempfile.TemporaryDirectory(
            dir=settings.BASE_DIR
        ) as media_root, override_settings(MEDIA_ROOT=media_root):
            default_storage.save(old_name, ContentFile(b"stored image"))
            image = EditorImage.objects.create(image=old_name, digest=digest)
            article = ArticleModel.objects.create(
                title="Legacy image path",
                content=f"![Legacy](/resources/{old_name})",
            )

            with self.captureOnCommitCallbacks(execute=True):
                migration.move_forward(apps, None)
            image.refresh_from_db()
            article.refresh_from_db()
            self.assertEqual(image.image.name, new_name)
            self.assertIn(f"/resources/{new_name}", article.content)
            self.assertTrue(default_storage.exists(new_name))
            self.assertFalse(default_storage.exists(old_name))

            with self.captureOnCommitCallbacks(execute=True):
                migration.move_backward(apps, None)
            image.refresh_from_db()
            article.refresh_from_db()
            self.assertEqual(image.image.name, old_name)
            self.assertIn(f"/resources/{old_name}", article.content)
            self.assertTrue(default_storage.exists(old_name))
            self.assertFalse(default_storage.exists(new_name))
