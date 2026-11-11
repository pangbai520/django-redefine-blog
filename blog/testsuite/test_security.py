import socket
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase

from blog.models import ArticleModel, EmbedProvider, SiteConfiguration
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

    def test_font_color(self):
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

    def test_hexo_html(self):
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

    def test_trusted_iframe(self):
        EmbedProvider.objects.create(
            name="Bilibili",
            host="player.bilibili.com",
            path_prefix="/player.html",
        )

        html = clean_html(
            '<iframe src="//player.bilibili.com/player.html?bvid=BV1&amp;p=1" '
            'width="960" height="540" allow="autoplay; fullscreen; camera" '
            'allowfullscreen style="position:fixed" srcdoc="bad" '
            'onload="alert(1)">fallback</iframe>'
        )

        self.assertIn('<iframe class="trusted-embed"', html)
        self.assertIn(
            'src="https://player.bilibili.com/player.html?bvid=BV1&amp;p=1"',
            html,
        )
        self.assertIn('loading="lazy"', html)
        self.assertIn('referrerpolicy="strict-origin-when-cross-origin"', html)
        self.assertIn('width="960"', html)
        self.assertIn('height="540"', html)
        self.assertIn('allow="autoplay; fullscreen"', html)
        self.assertIn(" allowfullscreen", html)
        self.assertNotIn("camera", html)
        self.assertNotIn("style=", html)
        self.assertNotIn("srcdoc", html)
        self.assertNotIn("onload", html)
        self.assertNotIn("fallback", html)

    def test_untrusted_iframe(self):
        EmbedProvider.objects.create(
            name="YouTube",
            host="www.youtube.com",
            path_prefix="/embed/",
        )

        samples = (
            '<iframe src="https://evil.example/embed/demo">fallback</iframe>',
            '<iframe src="http://www.youtube.com/embed/demo">fallback</iframe>',
            '<iframe src="https://www.youtube.com/watch?v=demo">fallback</iframe>',
            '<iframe src="https://www.youtube.com.evil.example/embed/demo">fallback</iframe>',
        )
        for sample in samples:
            with self.subTest(sample=sample):
                html = clean_html(sample)
                self.assertNotIn("<iframe", html)
                self.assertNotIn("fallback", html)

    def test_provider_cache(self):
        article = ArticleModel.objects.create(
            title="Embedded video",
            slug="embedded-video",
            content=(
                '<iframe src="https://www.youtube.com/embed/demo" '
                'allowfullscreen></iframe>'
            ),
        )
        self.assertNotIn("<iframe", str(article.html_content))

        provider = EmbedProvider.objects.create(
            name="YouTube",
            host="www.youtube.com",
            path_prefix="/embed/",
        )
        article = ArticleModel.objects.get(pk=article.pk)
        self.assertIn("<iframe", str(article.html_content))

        provider.enabled = False
        provider.save(update_fields=("enabled", "updated_at"))
        article = ArticleModel.objects.get(pk=article.pk)
        self.assertNotIn("<iframe", str(article.html_content))

    def test_provider_validation(self):
        invalid_rules = (
            ("https://player.example.com", "/embed/"),
            ("*.example.com", "/embed/"),
            ("player.example.com", "embed/"),
            ("player.example.com", "/embed/?unsafe=1"),
        )
        for host, path_prefix in invalid_rules:
            with self.subTest(host=host, path_prefix=path_prefix):
                provider = EmbedProvider(
                    name="Invalid",
                    host=host,
                    path_prefix=path_prefix,
                )
                with self.assertRaises(ValidationError):
                    provider.full_clean()


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
