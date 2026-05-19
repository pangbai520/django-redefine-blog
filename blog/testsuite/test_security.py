import socket
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from blog.models import ArticleModel, SiteConfiguration
from blog.services.emoji import _link_item
from blog.services.html_safety import clean_html
from blog.services.remote import RemoteFetchError, _check_url


class HtmlSafetyTests(TestCase):
    def setUp(self):
        SiteConfiguration.objects.create(config_name="Security", is_active=True)

    def test_active_html(self):
        article = ArticleModel.objects.create(
            title="Unsafe",
            slug="unsafe",
            content=(
                '<script>alert(1)</script>'
                '<img src="/safe.png" onerror="alert(2)">'
                '<a href="javascript:alert(3)">bad</a>'
            ),
        )

        html = str(article.html_content)
        self.assertNotIn("<script", html)
        self.assertNotIn("onerror", html)
        self.assertNotIn("javascript:", html)
        self.assertIn('src="/safe.png"', html)

    def test_theme_markup(self):
        html = clean_html(
            '<details class="folding"><summary>Title</summary>'
            '<div class="content markdown-body" data-tab="one">Body</div>'
            '<button type="button" aria-label="Copy">Copy</button></details>'
        )

        self.assertIn('<details class="folding">', html)
        self.assertIn('class="content markdown-body"', html)
        self.assertIn('data-tab="one"', html)
        self.assertIn('aria-label="Copy"', html)


class RemoteFetchTests(SimpleTestCase):
    def test_https_only(self):
        with self.assertRaises(RemoteFetchError):
            _check_url("http://emoji.example/info.json")

    @patch("blog.services.remote.socket.getaddrinfo")
    def test_private_ip(self, getaddrinfo):
        getaddrinfo.return_value = [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("127.0.0.1", 443),
            )
        ]

        with self.assertRaises(RemoteFetchError):
            _check_url("https://emoji.example/info.json")

    def test_emoji_origin(self):
        base = "https://cdn.example/emojis/demo"

        self.assertIsNone(_link_item(base, "https://tracker.example/pixel.png"))
        self.assertEqual(
            _link_item(base, "demo/happy.png")["url"],
            "https://cdn.example/emojis/demo/happy.png",
        )
