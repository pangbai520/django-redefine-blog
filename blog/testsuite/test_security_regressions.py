"""Regression coverage for the November 2026 source security review."""

from io import BytesIO
from unittest.mock import patch

from PIL import Image
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from blog.forms import UserProfileForm
from blog.models import ArticleModel, Comment, PendingRegistration, SiteConfiguration
from blog.services.tokens import registration_token_generator

User = get_user_model()
PASSWORD = "Regression-only-password!42"


class SecurityRegressionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.site = SiteConfiguration.objects.create(
            config_name="Security regression", is_active=True,
            comment_enabled=True, comment_system="internal",
            comment_email_notifications=False,
        )

    def activation_url(self, user, token=None):
        return reverse("comment_verify", args=[
            urlsafe_base64_encode(force_bytes(user.pk)),
            token or registration_token_generator.make_token(user),
        ])

    def pending_user(self, **flags):
        user = User.objects.create_user(
            "pending-reader", email="pending@example.invalid", password=PASSWORD,
            is_active=False, **flags,
        )
        PendingRegistration.objects.create(user=user)
        return user

    def test_suspended_accounts(self):
        for flags in ({}, {"is_staff": True}, {"is_staff": True, "is_superuser": True}):
            with self.subTest(flags=flags):
                cache.clear()
                user = User.objects.create_user(
                    f"suspended-{User.objects.count()}", email="suspended@example.invalid",
                    password=PASSWORD, is_active=False, **flags,
                )
                for route in ("comment_login", "comment_login_ajax"):
                    response = self.client.post(reverse(route), {
                        "username": user.username, "password": PASSWORD,
                    })
                    self.assertIn(response.status_code, (200, 401))
                user.refresh_from_db()
                self.assertFalse(user.is_active)
                self.assertFalse(PendingRegistration.objects.filter(user=user).exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_privileged_activation(self):
        for flags in ({"is_staff": True}, {"is_superuser": True}):
            with self.subTest(flags=flags):
                user = User.objects.create_user(
                    f"privileged-{User.objects.count()}", password=PASSWORD,
                    email="privileged@example.invalid", is_active=False, **flags,
                )
                PendingRegistration.objects.create(user=user)
                response = self.client.post(reverse("comment_login_ajax"), {
                    "username": user.username, "password": PASSWORD,
                })
                self.assertEqual(response.status_code, 401)
                self.assertEqual(self.client.post(self.activation_url(user)).status_code, 400)
                user.refresh_from_db()
                self.assertFalse(user.is_active)
        self.assertEqual(len(mail.outbox), 0)

    def test_registration_activation(self):
        user = self.pending_user()
        response = self.client.post(reverse("comment_login_ajax"), {
            "username": user.username, "password": PASSWORD,
        })
        self.assertEqual(response.status_code, 401)
        self.assertEqual(len(mail.outbox), 1)
        url = self.activation_url(user)
        self.assertEqual(self.client.get(url).status_code, 200)
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertEqual(self.client.post(url).status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertFalse(PendingRegistration.objects.filter(user=user).exists())
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        self.client.logout()
        self.client.post(url)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_reset_token(self):
        user = self.pending_user()
        url = self.activation_url(user, default_token_generator.make_token(user))
        self.assertEqual(self.client.post(url).status_code, 400)
        user.refresh_from_db()
        self.assertFalse(user.is_active)

    def test_replaced_registration(self):
        user = self.pending_user()
        url = self.activation_url(user)
        PendingRegistration.objects.filter(user=user).delete()
        PendingRegistration.objects.create(user=user)
        self.assertEqual(self.client.post(url).status_code, 400)

    def test_admin_revocation(self):
        user = self.pending_user()
        url = self.activation_url(user)
        # Admin saving an already-inactive unverified account revokes its grant.
        user.is_active = False
        user.save(update_fields=["is_active"])
        self.assertFalse(PendingRegistration.objects.filter(user=user).exists())
        self.assertEqual(self.client.post(url).status_code, 400)

    def test_activation_replay(self):
        user = self.pending_user()
        url = self.activation_url(user)
        self.client.post(url)
        user.refresh_from_db()
        user.is_active = False
        user.save(update_fields=["is_active"])
        self.client.logout()
        self.assertEqual(self.client.post(url).status_code, 400)
        response = self.client.post(reverse("comment_login_ajax"), {
            "username": user.username, "password": PASSWORD,
        })
        self.assertEqual(response.status_code, 401)
        self.assertFalse(PendingRegistration.objects.filter(user=user).exists())

    def test_delete_permission(self):
        inactive = SiteConfiguration.objects.create(config_name="Inactive")
        user = User.objects.create_user("limited-staff", is_staff=True)
        user.user_permissions.add(Permission.objects.get(codename="delete_standalonepage"))
        self.client.force_login(user)
        url = reverse("admin:blog_siteconfiguration_delete", args=[inactive.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {"post": "yes"}).status_code, 403)
        self.assertTrue(SiteConfiguration.objects.filter(pk=inactive.pk).exists())
        user.user_permissions.add(Permission.objects.get(codename="view_siteconfiguration"))
        response = self.client.post(reverse("admin:blog_siteconfiguration_changelist"), {
            "action": "delete_selected", "_selected_action": [inactive.pk], "post": "yes",
        })
        self.assertIn(response.status_code, (200, 302))
        self.assertTrue(SiteConfiguration.objects.filter(pk=inactive.pk).exists())

    def test_authorized_deletion(self):
        inactive = SiteConfiguration.objects.create(config_name="Inactive")
        user = User.objects.create_user("delete-staff", is_staff=True)
        user.user_permissions.add(*Permission.objects.filter(
            codename__in=["delete_siteconfiguration", "delete_standalonepage"],
        ))
        self.client.force_login(user)
        active_url = reverse("admin:blog_siteconfiguration_delete", args=[self.site.pk])
        self.assertEqual(self.client.post(active_url, {"post": "yes"}).status_code, 403)
        url = reverse("admin:blog_siteconfiguration_delete", args=[inactive.pk])
        self.assertEqual(self.client.post(url, {"post": "yes"}).status_code, 302)
        self.assertFalse(SiteConfiguration.objects.filter(pk=inactive.pk).exists())
        self.assertTrue(SiteConfiguration.objects.filter(pk=self.site.pk).exists())

    def make_comment(self, approved=True):
        user = User.objects.create_user("comment-author")
        article = ArticleModel.objects.create(
            title="Review", slug="review", content="Content", is_published=True,
        )
        comment = Comment.objects.create(
            article=article, author=user, content="Approved text", is_approved=approved,
        )
        self.client.force_login(user)
        return article, comment

    def test_edit_review(self):
        article, comment = self.make_comment()
        self.site.comment_auto_approve = False
        self.site.save(update_fields=["comment_auto_approve"])
        response = self.client.post(reverse("comment_edit", args=[comment.pk]), {
            "content": "Unreviewed replacement",
        })
        self.assertEqual(response.json(), {"ok": True, "pending": True})
        comment.refresh_from_db()
        self.assertFalse(comment.is_approved)
        self.assertEqual(Client().get(reverse("comment_list", args=[article.slug])).json()["comments"], [])

    def test_held_comment(self):
        _, comment = self.make_comment(approved=False)
        response = self.client.post(reverse("comment_edit", args=[comment.pk]), {"content": "New"})
        self.assertTrue(response.json()["pending"])
        comment.refresh_from_db()
        self.assertFalse(comment.is_approved)

    def test_approved_edit(self):
        _, comment = self.make_comment()
        response = self.client.post(reverse("comment_edit", args=[comment.pk]), {"content": "Updated"})
        self.assertEqual(response.json()["comment"]["content"], "Updated")

    def test_disabled_edit(self):
        _, comment = self.make_comment()
        self.site.comment_enabled = False
        self.site.save(update_fields=["comment_enabled"])
        response = self.client.post(reverse("comment_edit", args=[comment.pk]), {"content": "New"})
        self.assertEqual(response.status_code, 403)
        comment.refresh_from_db()
        self.assertEqual(comment.content, "Approved text")

    def avatar_form(self, dimensions=(32, 32), padding=b""):
        user = User.objects.create_user(f"avatar-{User.objects.count()}")
        data = BytesIO()
        Image.new("RGB", dimensions, "white").save(data, "PNG")
        upload = SimpleUploadedFile("avatar.png", data.getvalue() + padding, content_type="image/png")
        return UserProfileForm({
            "display_name": "Reader", "website": "", "avatar_crop_x": 0,
            "avatar_crop_y": 0, "avatar_crop_size": 1,
        }, {"avatar": upload}, instance=user.profile)

    def test_avatar_limits(self):
        for dimensions, padding in (((4097, 1), b""), ((8, 8), b"\x00" * (2 * 1024 * 1024))):
            with self.subTest(dimensions=dimensions, byte_padding=len(padding)):
                with patch("blog.forms.ImageOps.exif_transpose") as decode:
                    form = self.avatar_form(dimensions, padding)
                    self.assertFalse(form.is_valid())
                    self.assertIn("avatar", form.errors)
                    decode.assert_not_called()

    @override_settings(PROFILE_AVATAR_MAX_PIXELS=64)
    def test_avatar_pixels(self):
        with patch("blog.forms.ImageOps.exif_transpose") as decode:
            form = self.avatar_form((16, 16))
            self.assertFalse(form.is_valid())
            decode.assert_not_called()

    def test_valid_crop(self):
        form = self.avatar_form()
        self.assertTrue(form.is_valid(), form.errors)
        with Image.open(form.cleaned_data["avatar"]) as image:
            self.assertEqual(image.size, (512, 512))
            self.assertEqual(image.format, "WEBP")

    def test_shared_logins(self):
        user = User.objects.create_user("login-admin", password=PASSWORD, is_staff=True, is_superuser=True)
        for _ in range(10):
            self.assertEqual(self.client.post(reverse("comment_login_ajax"), {
                "username": user.username, "password": "wrong",
            }).status_code, 401)
        for route in ("admin:login", "comment_login", "comment_login_ajax"):
            with self.subTest(route=route):
                response = self.client.post(reverse(route), {"username": user.username, "password": PASSWORD})
                self.assertEqual(response.status_code, 429)
                self.assertEqual(response["Retry-After"], "900")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_ip(self):
        for number in range(11):
            response = self.client.post(reverse("admin:login"), {
                "username": f"missing-{number}", "password": "wrong",
            })
        self.assertEqual(response.status_code, 429)

    def test_login_account(self):
        for number in range(11):
            response = self.client.post(reverse("comment_login_ajax"), {
                "username": "same-account", "password": "wrong",
            }, REMOTE_ADDR=f"192.0.2.{number + 1}")
        self.assertEqual(response.status_code, 429)

    def test_admin_csrf(self):
        user = User.objects.create_user("csrf-admin", password=PASSWORD, is_staff=True, is_superuser=True)
        client = Client(enforce_csrf_checks=True)
        url = reverse("admin:login")
        client.get(url)
        self.assertEqual(client.post(url, {"username": user.username, "password": PASSWORD}).status_code, 403)
        response = client.post(url, {
            "username": user.username, "password": PASSWORD,
            "csrfmiddlewaretoken": client.cookies["csrftoken"].value,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(client.get(reverse("admin:index")).status_code, 200)
