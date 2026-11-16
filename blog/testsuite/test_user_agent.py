from django.test import SimpleTestCase

from blog.services.user_agent import parse_user_agent


class UserAgentTests(SimpleTestCase):
    def test_matches_waline_mobile_safari_fallback(self):
        user_agent = (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 15_6_1 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
            "Safari/603.2.4 MailMaster/7.19.6.2078"
        )
        self.assertEqual(
            parse_user_agent(user_agent),
            ("Mobile Safari", "iOS 15.6.1"),
        )

    def test_matches_waline_version_format(self):
        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/145.0.7632.117 Safari/537.36 "
            "Edg/145.0.3800.58"
        )
        self.assertEqual(parse_user_agent(user_agent), ("Edge145.0", "Windows 10"))

    def test_uses_platform_hint_for_windows_11(self):
        self.assertEqual(
            parse_user_agent(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/145.0.0.0",
                platform_version="15.0.0",
            ),
            ("Chrome145.0", "Windows 11"),
        )

    def test_preserves_linux_architecture(self):
        user_agent = "Mozilla/5.0 (X11; Linux x86_64) Firefox/145.0"
        self.assertEqual(parse_user_agent(user_agent), ("Firefox145.0", "Linux x86_64"))

    def test_recognizes_waline_browser_families_before_chromium(self):
        examples = (
            ("Mozilla/5.0 Android 15 Chrome/120.0 MiuiBrowser/19.3.2", "MIUI Browser19.3"),
            ("Mozilla/5.0 Windows NT 10.0 Chrome/120.0 QuarkPC/4.3.0", "Quark4.3"),
            ("Mozilla/5.0 Windows NT 10.0 Chrome/120.0 HBPC/15.0.3", "Huawei Browser15.0"),
            ("Mozilla/5.0 Android 12 Chrome/120.0 MQQBrowser/14.9", "QQBrowser14.9"),
            ("Mozilla/5.0 Android 12 Chrome/120.0 UCBrowser/15.1.8", "UCBrowser15.1"),
            ("Mozilla/5.0 Android 12 Chrome/120.0 MicroMessenger/8.0.55", "WeChat8.0"),
            ("Mozilla/5.0 Android 12 Chrome/120.0 SamsungBrowser/28.0", "Samsung Internet28.0"),
            ("Mozilla/5.0 Android 12 Chrome/120.0 VivoBrowser/25.8.0", "Vivo Browser25.8"),
            ("Mozilla/5.0 Android 12 Chrome/120.0 baiduboxapp/13.68.0", "Baidu13.68"),
        )
        for user_agent, expected in examples:
            with self.subTest(expected=expected):
                self.assertEqual(parse_user_agent(user_agent)[0], expected)

    def test_edge_marker_takes_precedence_over_embedded_quark_marker(self):
        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/132.0.0.0 "
            "Safari/537.36 Edg/132.0.0.0 Edge QuarkPC/2.0.1"
        )
        self.assertEqual(parse_user_agent(user_agent)[0], "Edge132.0")
