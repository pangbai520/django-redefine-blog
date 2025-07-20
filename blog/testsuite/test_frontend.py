from django.contrib.auth import get_user_model
from django.core.exceptions import FieldDoesNotExist
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase, override_settings
from markdown import Markdown

from core.markdown.extensions import get_extensions
from ..models import SiteConfiguration
from ..context_processors import site_processor

User = get_user_model()


class FrontendScriptTests(TestCase):
    def test_project_fields(self):
        for field_name in (
            "content_max_width",
            "toc_sidebar_width",
            "navbar_width_home",
            "navbar_width_pages",
            "article_font_size",
            "article_line_height",
            "article_image_border_radius",
            "heading_h1_top_spacing",
        ):
            with self.assertRaises(FieldDoesNotExist):
                SiteConfiguration._meta.get_field(field_name)

    def test_article_disabled(self):
        site = SiteConfiguration(toc_enabled=False)
        html = render_to_string("components/scripts.html", {"site": site})
        self.assertIn("js/plugins/tabs.js", html)
        self.assertNotIn("js/layouts/toc.js", html)

    def test_article_enabled(self):
        site = SiteConfiguration(toc_enabled=True)
        html = render_to_string("components/scripts.html", {"site": site})
        self.assertEqual(html.count("js/plugins/tabs.js"), 1)
        self.assertEqual(html.count("js/main.js"), 1)
        # main imports the TOC module through utils, so a second script tag
        # would register a duplicate page lifecycle
        self.assertNotIn("js/layouts/toc.js", html)

    @override_settings(
        SITE_CONTENT_MAXWIDTH=960,
        SITE_SIDEBAR_WIDTH=230,
        NAVBAR_WIDTH={"home": 1180, "pages": 940},
        ARTICLE_FONT_SIZE=18,
        ARTICLE_LINE_HEIGHT=1.7,
        ARTICLE_IMG_BORDER_RADIUS=12,
        ARTICLE_HEADINGS_TOP_SPACING={
            "h1": "3rem",
            "h2": "2rem",
            "h3": "1.8rem",
            "h4": "1.5rem",
            "h5": "1.3rem",
            "h6": "1.1rem",
        },
    )
    def test_theme_colours(self):
        site = SiteConfiguration(
            navbar_lcolor="#112233",
            navbar_rcolor="#abcdef",
            navbar_transparency=40,
        )
        context = site_processor(RequestFactory().get("/"))
        context["site"] = site
        html = render_to_string("components/header/theme-overrides.html", context)
        self.assertIn("--site-content-max-width: 960px", html)
        self.assertIn("--site-toc-sidebar-width: 230px", html)
        self.assertIn("--site-navbar-width-home: 1180px", html)
        self.assertIn("rgba(17, 34, 51, 0.251)", html)
        self.assertIn("rgba(171, 205, 239, 0.251)", html)
        self.assertIn("--site-article-font-size: 18px", html)
        self.assertIn("--site-article-line-height: 1.7", html)
        self.assertIn("margin-top: 2rem", html)
        self.assertIn("html.theme-switching *", html)
        self.assertIn("transition-duration: 0s !important", html)
        self.assertIn("::view-transition-new(root)", html)
        self.assertIn("theme-fade-in", html)

    def test_multiline_rendered(self):
        site = SiteConfiguration.objects.create(
            config_name="Template comment theme",
            colour_default_mode="light",
        )
        html = render_to_string("components/header/head.html", {"site": site})
        self.assertNotIn("{#", html)
        self.assertNotIn("Redefine's browser modules consume", html)

    def test_site_configuration(self):
        site = SiteConfiguration.objects.create(
            config_name="Admin-owned site identity",
            site_name="Admin Site",
            site_subname="Admin Subtitle",
            site_author="Admin Author",
            site_description="Admin Description",
            site_keywords="admin,site",
            google_analytics_enabled=True,
            google_analytics_id="G-TEST123",
            show_icp=True,
            icp_number="ICP 12345678",
            icp_url="https://beian.miit.gov.cn/",
        )
        request = RequestFactory().get("/")
        head = render_to_string(
            "components/header/head.html",
            {"site": site, "request": request, "SITE_LANG": "zh-CN"},
        )
        footer = render_to_string(
            "components/footer/footer.html",
            {
                "site": site,
                "articles_count": 0,
                "total_words": 0,
                "site_uv": 0,
                "site_pv": 0,
            },
        )

        self.assertIn('content="admin,site"', head)
        self.assertIn('content="Admin Description"', head)
        self.assertIn('content="Admin Author"', head)
        self.assertIn("G-TEST123", head)
        self.assertIn("Admin Site - Admin Subtitle", head)
        self.assertIn("ICP 12345678", footer)


class RedefineMarkdownTests(TestCase):
    def render(
        self,
        source,
        *,
        image_caption=False,
        lazyload=False,
        mermaid=False,
        delete_mask=False,
    ):
        site = SiteConfiguration(
            hyperlink_icon=True,
            article_image_description=image_caption,
            article_lazyload=lazyload,
            mermaid_enabled=mermaid,
            delete_mask=delete_mask,
        )
        return Markdown(extensions=get_extensions(site)).convert(source)

    def test_small_markdown(self):
        small = self.render(
            "{% note warning fa-circle-exclamation %}\n**Careful**\n{% endnote %}"
        )
        large = self.render(
            "{% notel info fa-circle-info Details %}\nA [link](https://external.invalid).\n{% endnotel %}"
        )

        self.assertIn(
            'class="note p-4 mb-4 rounded-small markdown-body warning icon-padding"',
            small,
        )
        self.assertIn('class="note-icon fa-solid fa-circle-exclamation"', small)
        self.assertIn("<strong>Careful</strong>", small)
        self.assertIn('class="note-large info"', large)
        self.assertIn("<p>Details</p>", large)
        self.assertIn('class="link"', large)

    def test_large_redefine(self):
        aliases = (
            "noteL",
            "notel",
            "notelarge",
            "notel-large",
            "notes-large",
            "subwarning",
        )
        for alias in aliases:
            with self.subTest(alias=alias):
                html = self.render(f"{{% {alias} %}}\nBody\n{{% end{alias} %}}")
                self.assertIn('class="note-large default"', html)
                self.assertIn("<p>Warning</p>", html)
                self.assertIn("<p>Body</p>", html)

        markdown_title = self.render(
            "{% notel info **Important** %}\nBody\n{% endnotel %}"
        )
        self.assertIn("<p><strong>Important</strong></p>", markdown_title)

    def test_tabs_order(self):
        html = self.render(
            "{% tabs Demo,2 %}\n"
            "<!-- tab First -->\nFirst pane\n<!-- endtab -->\n"
            "<!-- tab Second -->\n**Second pane**\n<!-- endtab -->\n"
            "{% endtabs %}"
        )

        self.assertIn('<div class="tabs" id="tab-demo">', html)
        self.assertIn('<ul class="nav-tabs">', html)
        self.assertIn('<li class="tab"><a class="#demo-1">First</a></li>', html)
        self.assertIn('<li class="tab active"><a class="#demo-2">Second</a></li>', html)
        self.assertIn('<div class="tab-pane active" id="demo-2">', html)
        self.assertIn("<strong>Second pane</strong>", html)

    def test_tab_code(self):
        html = self.render(
            "````html\n" "<!-- tab Not a tab -->\n" "```\n" "<!-- endtab -->\n" "````"
        )

        self.assertNotIn('<div class="tabs"', html)
        self.assertIn("Not a tab", html)

    def test_tabs_subtabs(self):
        html = self.render(
            "{% tabs Outer %}\n"
            "<!-- tab First@<i class='fa-solid fa-book'></i> -->\n"
            "{% subtabs Inner %}\n"
            "<!-- tab Nested -->\nNested content\n<!-- endtab -->\n"
            "{% endsubtabs %}\n"
            "<!-- endtab -->\n"
            "{% endtabs %}"
        )

        self.assertIn("fa-solid fa-book", html)
        self.assertIn("</i>First", html)
        self.assertIn('<div class="tabs" id="tab-outer">', html)
        self.assertIn('<div class="tabs" id="tab-inner">', html)
        self.assertIn("Nested content", html)

    def test_folding_structure(self):
        folding = self.render(
            "{% folding blue::More %}\n## Hidden heading\n{% endfolding %}"
        )
        buttons = self.render(
            "{% btn primary::Docs::https://example.com::fa-solid fa-book %}\n\n"
            "{% btns rounded %}\n"
            "{% cell Home::/::fa-solid fa-house %}\n"
            "{% cell Picture::/picture::/icon.png %}\n"
            "{% endbtns %}"
        )

        self.assertIn('<details class="blue" data-header-exclude="">', folding)
        self.assertIn('<p class="h2">Hidden heading</p>', folding)
        self.assertIn('class="button primary"', buttons)
        self.assertIn('class="btns rounded"', buttons)
        self.assertIn('class="fa-solid fa-house"', buttons)
        self.assertIn('<img src="/icon.png"', buttons)

    def test_image_setting(self):
        source = "![Landscape](/images/landscape.png)"
        disabled = self.render(source, image_caption=False)
        enabled = self.render(source, image_caption=True)

        self.assertNotIn("image-caption", disabled)
        self.assertIn('<figure class="image-caption">', enabled)
        self.assertIn("<figcaption>Landscape</figcaption>", enabled)

    def test_lazyload_attributes(self):
        source = "![Landscape](/images/landscape.png)"
        disabled = self.render(source, lazyload=False)
        enabled = self.render(source, lazyload=True)

        self.assertIn('src="/images/landscape.png"', disabled)
        self.assertIn('lazyload=""', enabled)
        self.assertIn('src="/static/images/loading.svg"', enabled)
        self.assertIn('data-src="/images/landscape.png"', enabled)

    def test_raw_filters(self):
        html = self.render(
            '<img class="hero" src="/images/raw.png" alt="Raw image">',
            image_caption=True,
            lazyload=True,
        )

        self.assertIn('<figure class="image-caption">', html)
        self.assertIn('class="hero"', html)
        self.assertIn('lazyload=""', html)
        self.assertIn('src="/static/images/loading.svg"', html)
        self.assertIn('data-src="/images/raw.png"', html)
        self.assertIn("<figcaption>Raw image</figcaption>", html)

    def test_mermaid_enabled(self):
        source = "```mermaid\ngraph TD\n  A --> B\n```"
        disabled = self.render(source, mermaid=False)
        enabled = self.render(source, mermaid=True)

        self.assertIn('class="iseeu highlight mermaid"', disabled)
        self.assertIn('<pre class="mermaid">graph TD\n  A --&gt; B</pre>', enabled)
        self.assertNotIn("code-container", enabled)

    def test_fenced_markers(self):
        tildes = self.render("~~~python\nprint('ok')\n~~~")
        long_fence = self.render("````text\n``` is content\n````")
        trailing = self.render("```text\nvalue\n```\n\nAfter")

        self.assertIn('data-language="python"', tildes)
        self.assertIn('class="hljs-variable">print</span>', tildes)
        self.assertIn('class="hljs-string">ok</span>', tildes)
        self.assertIn("``` is content", long_fence)
        self.assertIn("<p>After</p>", trailing)

    def test_strikethrough_pipeline(self):
        plain = self.render("~~hidden~~ and <del>raw</del>")
        masked = self.render("~~hidden~~ and <del>raw</del>", delete_mask=True)

        self.assertIn("<del>hidden</del>", plain)
        self.assertIn("<del>raw</del>", plain)
        self.assertIn('<del class="mask">hidden</del>', masked)
        self.assertIn('<del class="mask">raw</del>', masked)

    @override_settings(ALLOWED_HOSTS=["blog.example.com"])
    def test_link_links(self):
        html = self.render(
            "[internal](https://blog.example.com/about) "
            "[subdomain](https://static.blog.example.com/file) "
            "[external](https://example.net) "
            "[![image](/image.png)](https://example.net/image)"
        )

        self.assertNotIn('href="https://blog.example.com/about" rel=', html)
        self.assertNotIn('href="https://static.blog.example.com/file" rel=', html)
        self.assertIn(
            'class="link" href="https://example.net" rel="noopener" target="_blank"',
            html,
        )
        self.assertEqual(html.count('class="link"'), 1)

    def test_gfm_checkboxes(self):
        html = self.render("- [x] shipped **now**\n- [ ] pending")

        self.assertIn('<ul class="contains-task-list">', html)
        self.assertEqual(html.count('class="task-list-item"'), 2)
        self.assertIn('checked="checked"', html)
        self.assertEqual(html.count('disabled="disabled"'), 2)
        self.assertRegex(html, r"<input[^>]+ /> shipped <strong>now</strong>")

    def test_unclosed_markdown(self):
        html = self.render("{% note warning %}\nVisible\n\n## Still here")

        self.assertIn("{% note warning %}", html)
        self.assertIn("Visible", html)
        self.assertIn("Still here", html)

    def test_runtime_configuration(self):
        site = SiteConfiguration.objects.create(
            config_name="Runtime theme options",
            article_lazyload=False,
            article_pangu_js=True,
        )
        head = render_to_string("components/header/head.html", {"site": site})
        scripts = render_to_string("components/scripts.html", {"site": site})

        self.assertNotIn("preload:", head)
        self.assertIn('path: "/search.json"', head)
        self.assertIn("lazyload: false", head)
        self.assertIn("js/libs/pangu.min.js", scripts)
