import json
from urllib.parse import parse_qs
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from ..models import ArticleModel, Comment, SiteConfiguration
from ..services.turnstile import verify_turnstile


User = get_user_model()
TURNSTILE = {
    "TURNSTILE_ENABLED": True,
    "TURNSTILE_SITE_KEY": "site-key",
    "TURNSTILE_SECRET_KEY": "secret-key",
}


class _VerificationResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


@override_settings(**TURNSTILE)
class TurnstileTests(TestCase):
    def setUp(self):
        cache.clear()
        self.site = SiteConfiguration.objects.create(
            config_name="Turnstile",
            site_name="Turnstile Blog",
            is_active=True,
            comment_enabled=True,
            comment_system="internal",
            comment_allow_guest=True,
            comment_require_login=False,
        )
        self.article = ArticleModel.objects.create(
            title="Protected article",
            slug="protected-article",
            content="Body",
            is_published=True,
        )

    @patch("blog.services.turnstile.urlopen")
    @override_settings(TRUST_X_FORWARDED_FOR=True)
    def test_server_action(self, mocked_open):
        mocked_open.return_value = _VerificationResponse(
            {"success": True, "action": "register"}
        )
        request = RequestFactory().post(
            "/comments/register/",
            {"cf-turnstile-response": "valid-token"},
            HTTP_X_FORWARDED_FOR="203.0.113.7, 10.0.0.1",
        )

        self.assertTrue(verify_turnstile(request, "register"))
        verification = mocked_open.call_args.args[0]
        payload = parse_qs(verification.data.decode())
        self.assertEqual(payload["secret"], ["secret-key"])
        self.assertEqual(payload["response"], ["valid-token"])
        self.assertEqual(payload["remoteip"], ["203.0.113.7"])
        self.assertFalse(verify_turnstile(request, "password_reset"))

    def test_register_token(self):
        response = self.client.post(
            reverse("comment_register_ajax"),
            {
                "username": "robot",
                "email": "robot@example.com",
                "password": "A-strong-password-123",
                "password_confirm": "A-strong-password-123",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(username="robot").exists())

    def test_reset_token(self):
        response = self.client.post(
            reverse("password_reset"),
            {"email": "reader@example.com"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(mail.outbox, [])

    def test_guest_condition(self):
        article_url = reverse("article", args=[self.article.slug])
        page = self.client.get(article_url)
        self.assertContains(page, 'data-action="guest_comment"')

        response = self.client.post(
            reverse("comment_create", args=[self.article.slug]),
            {"nickname": "Guest", "content": "No token"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Comment.objects.exists())

        self.site.comment_require_login = True
        self.site.save(update_fields=("comment_require_login",))
        cache.clear()
        locked = self.client.get(article_url)
        self.assertNotContains(locked, 'data-action="guest_comment"')

    def test_member_bypass(self):
        user = User.objects.create_user("reader", password="password-for-tests")
        self.client.force_login(user)

        response = self.client.post(
            reverse("comment_create", args=[self.article.slug]),
            {"content": "Signed in"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Comment.objects.filter(author=user).exists())

    @patch("blog.comment_views._rate_limited", return_value=True)
    @patch("blog.services.turnstile.urlopen")
    def test_member_challenge(self, mocked_open, _limited):
        user = User.objects.create_user("busy-reader", password="password-for-tests")
        self.client.force_login(user)
        endpoint = reverse("comment_create", args=[self.article.slug])
        page = self.client.get(reverse("article", args=[self.article.slug]))

        self.assertContains(page, 'data-action="member_comment"')

        challenged = self.client.post(endpoint, {"content": "Too fast"})

        self.assertEqual(challenged.status_code, 429)
        self.assertTrue(challenged.json()["turnstile_required"])
        self.assertFalse(Comment.objects.exists())

        mocked_open.return_value = _VerificationResponse(
            {"success": True, "action": "member_comment"}
        )
        accepted = self.client.post(
            endpoint,
            {"content": "Verified", "cf-turnstile-response": "valid-token"},
        )

        self.assertEqual(accepted.status_code, 200)
        self.assertTrue(Comment.objects.filter(author=user, content="Verified").exists())

    @override_settings(TURNSTILE_ENABLED=False)
    @patch("blog.comment_views._rate_limited", return_value=True)
    def test_member_limit(self, _limited):
        user = User.objects.create_user("limited-reader", password="password-for-tests")
        self.client.force_login(user)

        response = self.client.post(
            reverse("comment_create", args=[self.article.slug]),
            {"content": "Still limited"},
        )

        self.assertEqual(response.status_code, 429)
        self.assertNotIn("turnstile_required", response.json())
        self.assertFalse(Comment.objects.exists())

    def test_public_forms(self):
        register = self.client.get(reverse("comment_register"))
        reset = self.client.get(reverse("password_reset"))

        self.assertContains(register, 'data-action="register"')
        self.assertContains(reset, 'data-action="password_reset"')
        self.assertContains(register, "js/turnstile.js")
        self.assertContains(register, "challenges.cloudflare.com/turnstile/")
