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
                '<style>body{display:none}</style>'
                '<iframe src="https://evil.example"></iframe>'
                '<object data="https://evil.example/payload"></object>'
                '<link rel="stylesheet" href="https://evil.example/style.css">'
                '<img src="/safe.png" onerror="alert(2)">'
                '<a href="javascript:alert(3)">bad</a>'
            ),
        )

        html = str(article.html_content)
        self.assertNotIn("<script", html)
        self.assertNotIn("<style", html)
        self.assertNotIn("<iframe", html)
        self.assertNotIn("<object", html)
        self.assertNotIn("<link", html)
        self.assertNotIn("evil.example", html)
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

    def test_legacy_font_color(self):
        article = ArticleModel.objects.create(
            title="Colored text",
            slug="colored-text",
            content=(
                '<font color=FF3030>plain hex</font> '
                '<font color="#FF3030" onclick="alert(1)" style="display:none">'
                "hash hex</font>"
            ),
        )

        html = str(article.html_content)
        self.assertIn('<font color="FF3030">plain hex</font>', html)
        self.assertIn('<font color="#FF3030">hash hex</font>', html)
        self.assertNotIn("onclick", html)
        self.assertNotIn("style=", html)

    def test_safe_hexo_html(self):
        html = clean_html(
            '<a href="/file.zip" download="file.zip" rel="nofollow">download</a>'
            '<font color="red" face="serif" size="3">legacy</font>'
            '<picture><source srcset="/large.webp" type="image/webp">'
            '<img src="/small.png" alt="sample"></picture>'
            '<audio src="/song.mp3" controls preload="metadata"></audio>'
            '<video src="/clip.mp4" controls playsinline width="640"></video>'
        )

        self.assertIn('download="file.zip"', html)
        self.assertIn('face="serif"', html)
        self.assertIn('<picture>', html)
        self.assertIn('<source srcset="/large.webp" type="image/webp">', html)
        self.assertIn('<audio src="/song.mp3" controls', html)
        self.assertIn('<video src="/clip.mp4" controls', html)


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
