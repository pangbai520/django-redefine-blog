from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in
from django.test import RequestFactory, TestCase
from django.urls import reverse

from blog.models import AdminLoginRecord


class AdminLoginAuditTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="site-owner",
            email="owner@example.com",
            password="Strong-test-password-123",
        )

    def test_admin_login(self):
        response = self.client.post(
            reverse("admin:login"),
            {
                "username": self.user.username,
                "password": "Strong-test-password-123",
                "next": reverse("admin:index"),
            },
            REMOTE_ADDR="192.0.2.45",
            HTTP_USER_AGENT="Audit browser",
        )

        self.assertEqual(response.status_code, 302)
        record = AdminLoginRecord.objects.get()
        self.assertEqual(record.user, self.user)
        self.assertEqual(record.username, "site-owner")
        self.assertEqual(record.ip_address, "192.0.2.45")
        self.assertEqual(record.user_agent, "Audit browser")
        self.assertNotIn("Strong-test-password-123", str(record.__dict__))

    def test_non_admin(self):
        request = RequestFactory().post("/comments/login/")
        user_logged_in.send(
            sender=get_user_model(),
            request=request,
            user=self.user,
        )

        self.assertFalse(AdminLoginRecord.objects.exists())

    def test_readonly_admin(self):
        model_admin = admin.site._registry[AdminLoginRecord]
        request = RequestFactory().get(reverse("admin:blog_adminloginrecord_changelist"))
        request.user = self.user

        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))
