import re
from functools import cached_property

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from blog.validators import validate_theme_image

CACHE_KEY = "actived_site_config"
CACHE_TIMEOUT = 60 * 60 * 24


class SiteConfiguration(models.Model):
    config_name = models.CharField(
        "Configuration name", max_length=50, default="Default Config"
    )
    is_active = models.BooleanField(
        "Set as the currently active configuration", default=False
    )
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    site_name = models.CharField(
        _("site name"), max_length=200, default="Django Redefine"
    )
    site_subname = models.CharField(
        _("site info subtitle"),
        max_length=200,
        blank=True,
        null=True,
        default="Redefine Your Django Journey.",
    )
    site_author = models.CharField(
        _("site author"), max_length=100, default="The Redefine Team"
    )
    site_description = models.TextField(
        _("site description"),
        max_length=500,
        blank=True,
        default="",
    )
    site_keywords = models.CharField(
        _("site keywords"),
        max_length=500,
        blank=True,
        default="",
        help_text="Comma-separated keywords used by search engines.",
    )

    site_avatar = models.FileField(
        upload_to="avatar/",
        blank=True,
        null=True,
        validators=[validate_theme_image],
    )
    site_logo = models.FileField(
        upload_to="logo/",
        blank=True,
        null=True,
        validators=[validate_theme_image],
    )
    site_favicon = models.FileField(
        upload_to="favicon/",
        blank=True,
        null=True,
        validators=[validate_theme_image],
    )

    colour_primary = models.CharField(max_length=20, default="#A31F34")
    colour_default_mode = models.CharField(
        _("default mode"),
        max_length=50,
        choices=[
            ("light", "Light"),
            ("dark", "Dark"),
        ],
        default="light",
    )

    effect_hover_shadow = models.BooleanField(default=True)
    effect_hover_scale = models.BooleanField(default=False)

    # split bar and percentage visibility, matching Redefine's two progress controls
    reading_bar_enabled = models.BooleanField(default=False)
    reading_bar_percentage = models.BooleanField(default=True)
    website_counter_enabled = models.BooleanField(default=True)
    website_counter_site_pv = models.BooleanField(default=True)
    website_counter_site_uv = models.BooleanField(default=True)
    website_counter_post_pv = models.BooleanField(default=True)

    swup_enabled = models.BooleanField(default=True)

    # allow social previews to differ from ordinary page metadata
    og_enabled = models.BooleanField(default=True)
    og_image = models.FileField(
        upload_to="opengraph/",
        blank=True,
        null=True,
        validators=[validate_theme_image],
    )
    og_description = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        default="Django Redefine, Redefine Your Django Journey.",
    )

    preloader_enabled = models.BooleanField(default=False)
    preloader_message = models.CharField(max_length=100, blank=True, default="")

    # preserve Redefine's compact side-tool behavior as reader-facing switches
    sidetools_gear_rotation = models.BooleanField(default=True)
    sidetools_auto_expand = models.BooleanField(default=False)

    # load optional Font Awesome families only when configured icons need them
    fontawesome_thin = models.BooleanField(default=False)
    fontawesome_light = models.BooleanField(default=False)
    fontawesome_duotone = models.BooleanField(default=False)
    fontawesome_sharp_solid = models.BooleanField(default=False)

    homebanner_enabled = models.BooleanField(default=True)
    homebanner_style = models.CharField(
        max_length=10,
        choices=[("static", "Static"), ("fixed", "Fixed")],
        default="fixed",
    )
    light_image = models.FileField(
        upload_to="banner/",
        blank=True,
        null=True,
        validators=[validate_theme_image],
    )
    dark_image = models.FileField(
        upload_to="banner/",
        blank=True,
        null=True,
        validators=[validate_theme_image],
    )
    hb_title = models.CharField(max_length=100, default="Django Redefine")
    subtitle_enabled = models.BooleanField(default=False)
    subtitle_text = models.JSONField(default=list, blank=True)
    st_hitokoto_enable = models.BooleanField(default=False)
    st_hitokoto_show_author = models.BooleanField(default=False)
    st_hitokoto_api = models.URLField(default="https://v1.hitokoto.cn")
    st_typing_speed = models.PositiveIntegerField(default=100)
    st_backing_speed = models.PositiveIntegerField(default=80)
    st_starting_delay = models.PositiveIntegerField(default=500)
    st_backing_delay = models.PositiveIntegerField(default=1500)
    subtitle_loop = models.BooleanField(default=True)
    st_smart_backspace = models.BooleanField(default=True)

    hb_light_text = models.CharField(max_length=20, default="#fff")
    hb_dark_text = models.CharField(max_length=20, default="#d1d1b6")

    text_title_size = models.FloatField(default=2.8)
    text_subtitle_size = models.FloatField(default=1.5)
    text_line_height = models.FloatField(default=1.2)

    social_links_enabled = models.BooleanField(default=False)
    social_links_style = models.CharField(
        max_length=20,
        choices=[("default", "Default"), ("reverse", "Reverse"), ("center", "Center")],
        default="default",
    )

    navbar_autohide = models.BooleanField(default=False)
    navbar_lcolor = models.CharField(max_length=20, default="#f78736")
    navbar_rcolor = models.CharField(max_length=20, default="#367df7")
    navbar_transparency = models.PositiveIntegerField(default=35)
    navbar_search_enabled = models.BooleanField(default=False)
    # Kept for database compatibility with existing sites. Server-side search
    # no longer downloads or preloads the complete article corpus.
    navbar_search_preload = models.BooleanField(default=True)

    sidebar_enabled = models.BooleanField(default=True)
    sidebar_position = models.CharField(
        max_length=10, choices=[("left", "Left"), ("right", "Right")], default="left"
    )
    sidebar_firstitem = models.CharField(
        max_length=20, choices=[("menu", "Menu"), ("info", "Info")], default="menu"
    )
    sidebar_announcement = models.CharField(max_length=200, blank=True)
    sidebar_on_mobile = models.BooleanField(default=True)
    comment_enabled = models.BooleanField(default=False)
    comment_system = models.CharField(
        max_length=20,
        choices=[
            ("waline", "Waline"),
            ("gitalk", "Gitalk"),
            ("twikoo", "Twikoo"),
            ("giscus", "Giscus"),
            ("internal", "本站评论系统"),
        ],
        blank=True,
        default="",
    )
    comment_require_login = models.BooleanField(
        "Require login to comment",
        default=False,
        help_text="When enabled, visitors must sign in before posting comments.",
    )
    comment_auto_approve = models.BooleanField(
        "Auto approve comments",
        default=True,
        help_text="Disable this to review new comments in the admin site first.",
    )
    comment_email_notifications = models.BooleanField(
        "Email notifications",
        default=True,
        help_text="Send reply and like notifications to registered users.",
    )
    comment_registration_enabled = models.BooleanField(
        "Allow registration",
        default=True,
        help_text="Allow visitors to create an account for the internal comment system.",
    )
    comment_require_email_verification = models.BooleanField(
        "Require email verification",
        default=True,
        help_text="New accounts must verify their email address before commenting.",
    )
    comment_profile_review_enabled = models.BooleanField(
        _("Review profile changes"),
        default=False,
        help_text=(
            "Hold new display names and avatars for administrator approval. "
            "Staff and superusers are not held for review."
        ),
    )
    comment_allow_likes = models.BooleanField("Allow comment likes", default=True)
    comment_allow_guest = models.BooleanField("Allow guest comments", default=True)
    comment_emoji_enabled = models.BooleanField("Enable emoji picker", default=True)
    comment_gif_enabled = models.BooleanField("Enable GIF picker", default=True)
    comment_config = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Use the original Redefine structure: {waline: {...}, gitalk: {...}, "
            "twikoo: {...}, giscus: {...}}."
        ),
    )
    article_dateformat = models.CharField(
        max_length=50,
        default="auto",
        help_text=(
            "Use auto, relative, or a Moment.js-style format such as "
            "YYYY-MM-DD, YYYY/MM/DD HH:mm, or MMM D, YYYY."
        ),
    )
    article_excerpt_length = models.PositiveIntegerField(default=200)
    article_categories_enabled = models.BooleanField(default=True)
    article_categories_limit = models.PositiveIntegerField(default=3)
    article_tags_enabled = models.BooleanField(default=True)
    article_tags_limit = models.PositiveIntegerField(default=3)

    article_image_alignment = models.CharField(
        max_length=10,
        choices=[("left", "Left"), ("center", "Center")],
        default="center",
    )
    article_image_description = models.BooleanField(default=False)
    hyperlink_icon = models.BooleanField(default=True)
    delete_mask = models.BooleanField(default=False)
    title_alignment = models.CharField(
        max_length=10, choices=[("left", "Left"), ("center", "Center")], default="left"
    )
    COPYRIGHT_CHOICES = [
        ("cc_by_nc_sa", "CC BY-NC-SA"),
        ("cc_by_nd", "CC BY-ND"),
        ("cc_by_nc", "CC BY-NC"),
        ("cc_by_sa", "CC BY-SA"),
        ("cc_by", "CC BY"),
        ("all_rights_reserved", "All Rights Reserved"),
        ("public_domain", "Public Domain"),
    ]
    copyright_enabled = models.BooleanField(default=True)
    copyright_type = models.CharField(
        max_length=50,
        choices=COPYRIGHT_CHOICES,
        default="cc_by_nc_sa",
    )
    counter_enabled = models.BooleanField(default=True)
    show_word_counter = models.BooleanField(default=True)
    show_reading_time = models.BooleanField(default=True)

    author_label_enabled = models.BooleanField(default=True)
    author_label_auto = models.BooleanField(default=False)
    author_label_list = models.JSONField(default=list, blank=True)
    code_block_copy = models.BooleanField(default=True)
    code_block_style = models.CharField(
        max_length=10, choices=[("mac", "Mac"), ("simple", "Simple")], default="mac"
    )
    codeblock_light = models.CharField(
        max_length=50,
        choices=[
            ("github", "GitHub"),
            ("atom-one-light", "Atom One Light"),
            ("default", "Default"),
        ],
        default="github",
    )
    codeblock_dark = models.CharField(
        max_length=50,
        choices=[
            ("github-dark", "GitHub Dark"),
            ("monokai-sublime", "Monokai Sublime"),
            ("vs2015", "VS2015"),
            ("night-owl", "Night Owl"),
            ("atom-one-dark", "Atom One Dark"),
            ("nord", "Nord"),
            ("tokyo-night-dark", "Tokyo Night Dark"),
            ("a11y-dark", "A11y Dark"),
            ("agate", "Agate"),
        ],
        default="vs2015",
    )
    # mirror Redefine's TOC depth, numbering and initial expansion controls
    toc_enabled = models.BooleanField(default=True)
    toc_max_depth = models.PositiveIntegerField(default=3)
    toc_has_number = models.BooleanField(default=False)
    toc_expand = models.BooleanField(default=True)
    toc_init_open = models.BooleanField(default=True)
    article_lazyload = models.BooleanField(default=True)
    article_pangu_js = models.BooleanField(default=False)
    recommendation_enabled = models.BooleanField(default=False)
    recommendation_title = models.CharField(max_length=50, default="推荐阅读")
    recommendation_limit = models.PositiveIntegerField(default=3)
    recommendation_mobile_limit = models.PositiveIntegerField(default=2)
    recommendation_placeholder = models.FileField(
        upload_to="recommendation/",
        blank=True,
        null=True,
        validators=[validate_theme_image],
    )
    recommendation_skip_dirs = models.JSONField(default=list, blank=True)

    footer_runtime_enabled = models.BooleanField(default=True)
    footer_icon = models.CharField(
        max_length=200,
        blank=True,
        default=(
            '<i class="fa-solid fa-heart fa-beat" '
            'style="--fa-animation-duration: 0.5s; color: #f54545"></i>'
        ),
    )
    footer_sitestart = models.DateTimeField(
        max_length=50, blank=True, default=timezone.now
    )
    footer_statistics = models.BooleanField(default=True)
    footer_content = models.CharField(max_length=200, blank=True)
    show_icp = models.BooleanField(default=False)
    icp_number = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text='For example: "ICP 12345678".',
    )
    icp_url = models.URLField(
        default="https://beian.miit.gov.cn/",
        blank=True,
    )

    google_analytics_enabled = models.BooleanField(default=False)
    google_analytics_id = models.CharField(max_length=50, blank=True, default="")

    # allow trusted administrators to add optional integrations without editing templates
    inject_enabled = models.BooleanField(default=False)
    inject_header = models.TextField(blank=True)
    inject_footer = models.TextField(blank=True)

    rssfeed_enabled = models.BooleanField(default=False)
    rssfeed_url = models.URLField(blank=True)
    aplayer_enabled = models.BooleanField(default=False)
    aplayer_type = models.CharField(
        max_length=10,
        choices=(
            ("fixed", "Fixed (底部固定播放器)"),
            ("mini", "Mini (迷你播放器)"),
        ),
        default="fixed",
    )
    aplayer_config = models.JSONField(default=dict, blank=True)
    mermaid_enabled = models.BooleanField(default=False)

    bookmarks_enabled = models.BooleanField(default=False)
    essays_enabled = models.BooleanField(default=False)
    masonry_enabled = models.BooleanField(default=False)
    friends_enabled = models.BooleanField(default=True)
    friends_page_columns = models.PositiveIntegerField(
        choices=[(2, "2 Column"), (3, "3 Column")],
        default=2,
    )
    tags_page_style = models.CharField(
        max_length=20, choices=[("blur", "Blur"), ("cloud", "Cloud")], default="blur"
    )

    @property
    def enabled_fonts(self):
        return self.fonts.filter(enabled=True).exclude(url="")

    @cached_property
    def font_settings(self):
        """Return one enabled font configuration for each Redefine font slot."""
        if not self.pk:
            return {}
        return {
            font.type: font
            for font in self.fonts.filter(enabled=True).exclude(family="")
        }

    @staticmethod
    def _rgba(hex_color, opacity):
        """Reproduce Redefine's two-digit hexadecimal alpha setting."""
        value = (hex_color or "").strip().lstrip("#")
        if len(value) == 3:
            value = "".join(char * 2 for char in value)
        if not re.fullmatch(r"[0-9a-fA-F]{6}", value):
            value = "000000"
        red, green, blue = (int(value[index : index + 2], 16) for index in (0, 2, 4))
        alpha_token = min(max(int(opacity or 0), 0), 100)
        if alpha_token == 100:
            alpha = 1
        else:
            # The upstream theme appends values such as "35" to a six-digit
            # colour as an alpha byte (#RRGGBB35), rather than treating 35 as
            # 35 percent. Keeping that behaviour preserves its softer navbar.
            alpha = int(f"{alpha_token:02d}", 16) / 255
        alpha_text = f"{alpha:.3f}".rstrip("0").rstrip(".")
        return f"rgba({red}, {green}, {blue}, {alpha_text})"

    @property
    def navbar_left_rgba(self):
        return self._rgba(self.navbar_lcolor, self.navbar_transparency)

    @property
    def navbar_right_rgba(self):
        return self._rgba(self.navbar_rcolor, self.navbar_transparency)

    @property
    def aplayer_tracks(self):
        from .collections import AudioTrack

        tracks = []
        for track in AudioTrack.objects.filter(enabled=True):
            tracks.append(
                {
                    "name": track.name,
                    "artist": track.artist,
                    "url": track.audio_file.url if track.audio_file else track.url,
                    "cover": (
                        track.cover_image.url if track.cover_image else track.cover
                    ),
                    "lrc": track.lrc,
                    "theme": track.theme,
                }
            )
        return tracks

    @property
    def aplayer_settings(self):
        """Return advanced options with the selected display mode applied."""
        settings = (
            self.aplayer_config.copy() if isinstance(self.aplayer_config, dict) else {}
        )
        settings["type"] = self.aplayer_type or settings.get("type", "fixed")
        return settings

    @property
    def aplayer_is_mini(self):
        return self.aplayer_settings["type"] == "mini"

    def _comment_opts(self, *, secrets=False):
        """Normalize provider options and hide server-only values by default."""
        raw = self.comment_config if isinstance(self.comment_config, dict) else {}
        options = raw.get(self.comment_system, raw)
        if not isinstance(options, dict):
            return {}

        aliases = {
            "serverUrl": "server_url",
            "clientID": "client_id",
            "clientSecret": "client_secret",
            "repo_id": "repo_id",
            "category_id": "category_id",
        }
        normalized = dict(options)
        for canonical, legacy in aliases.items():
            if canonical not in normalized and legacy in normalized:
                normalized[canonical] = normalized[legacy]
        if self.comment_system == "gitalk" and not secrets:
            for key in ("clientSecret", "client_secret", "proxy"):
                normalized.pop(key, None)
        if self.comment_system == "waline":
            normalized.setdefault("lang", "zh-CN")
        return normalized

    @property
    def comment_options(self):
        """Return only browser-safe options for the active comment provider."""
        return self._comment_opts()

    def server_comment_options(self):
        """Return provider credentials for trusted server-side code."""
        return self._comment_opts(secrets=True)

    @property
    def social_layout(self):
        """Return the utility classes used by the social-links layout."""
        if self.social_links_style == "center":
            return {
                "justify": "justify-center",
                "display": "hidden",
                "flex_dir": "flex-row",
            }
        return {
            "justify": "justify-between",
            "display": "flex",
            "flex_dir": (
                "flex-row-reverse"
                if self.social_links_style == "reverse"
                else "flex-row"
            ),
        }

    @property
    def social_links(self):
        """Return social links belonging to this configuration."""
        return self.links.filter(link_location="social")

    @property
    def qrcode_links(self):
        """Return QR-code links belonging to this configuration."""
        return self.links.filter(link_location="qrs")

    @property
    def navbar_links(self):
        # return roots only; dropdown children are rendered by their parent
        return (
            self.links.filter(link_location="navbar", parent__isnull=True)
            .prefetch_related("translations", "submenus__translations")
            .order_by("order")
        )

    @property
    def sidebar_links(self):
        """Return links assigned to the sidebar."""
        return (
            self.links.filter(link_location="sidebar")
            .prefetch_related("translations")
            .order_by("order")
        )

    @property
    def mobile_sidebar_links(self):
        """Avoid repeating links already present in the mobile navbar."""
        navbar = self.links.filter(link_location="navbar", parent__isnull=True)
        navbar_urls = set(navbar.values_list("url", flat=True))
        navbar_names = {
            name.casefold() for name in navbar.values_list("name", flat=True)
        }
        return [
            link
            for link in self.sidebar_links
            if link.url not in navbar_urls and link.name.casefold() not in navbar_names
        ]

    @classmethod
    def get_config(cls):
        site = cache.get(CACHE_KEY)
        if not site:
            site = cls.load()
            cache.set(CACHE_KEY, site, 3600)
        return site

    class Meta:
        verbose_name = "Site Configuration"
        verbose_name_plural = "Site Configurations"
        constraints = [
            models.UniqueConstraint(
                fields=("is_active",),
                condition=Q(is_active=True),
                name="unique_active_site_configuration",
            ),
        ]

    def __str__(self):
        return self.config_name

    def clean(self):
        """Prevent saving a configuration when it would remove the active site."""
        errors = {}
        if self.comment_enabled and not self.comment_system:
            errors["comment_system"] = "启用评论后必须选择评论系统。"
        if (
            self.subtitle_enabled
            and not self.st_hitokoto_enable
            and not (isinstance(self.subtitle_text, list) and self.subtitle_text)
        ):
            errors["subtitle_text"] = "启用副标题后，请填写文本列表或启用一言。"
        if (
            self.google_analytics_enabled
            and not (self.google_analytics_id or "").strip()
        ):
            errors["google_analytics_id"] = (
                "A measurement ID is required when Google Analytics is enabled."
            )
        if self.show_icp and not (self.icp_number or "").strip():
            errors["icp_number"] = (
                "An ICP number is required when ICP information is enabled."
            )

        ranges = {
            "navbar_transparency": (0, 100),
            "toc_max_depth": (1, 6),
            "text_title_size": (0.5, 10),
            "text_subtitle_size": (0.5, 10),
            "text_line_height": (1, 5),
            "article_categories_limit": (0, 100),
            "article_tags_limit": (0, 100),
            "recommendation_limit": (1, 100),
            "recommendation_mobile_limit": (1, 100),
        }
        for field_name, (minimum, maximum) in ranges.items():
            value = getattr(self, field_name)
            if not minimum <= value <= maximum:
                errors[field_name] = f"请输入 {minimum} 到 {maximum} 之间的值。"

        if self.pk and not self.is_active:
            other_active_exists = (
                SiteConfiguration.objects.filter(is_active=True)
                .exclude(pk=self.pk)
                .exists()
            )
            if not other_active_exists:
                errors["is_active"] = "🚨 操作失败：必须保留至少一个激活的配置文件！"

        if errors:
            raise ValidationError(errors)

    def validate_constraints(self, exclude=None):
        # save() deactivates the previous configuration before this row is
        # written; skip the pre-save uniqueness probe and let the database
        # enforce the same invariant without rejecting a valid switch
        excluded = set(exclude or ())
        excluded.add("is_active")
        return super().validate_constraints(exclude=excluded)

    @property
    def rss_url(self):
        """Use an external feed when configured, otherwise expose the native feed."""
        return (self.rssfeed_url or "").strip() or reverse("article_feed")

    @classmethod
    def load(cls):
        obj = cls.objects.filter(is_active=True).first()

        if not obj:
            obj = cls.objects.first()

        if not obj:
            obj = cls.objects.create(config_name="Default Config", is_active=True)
        return obj

    def save(self, *args, **kwargs):
        validate = kwargs.pop("validate", True)
        if validate:
            self.full_clean(validate_constraints=False)
        with transaction.atomic():
            if self.is_active:
                SiteConfiguration.objects.filter(is_active=True).exclude(
                    pk=self.pk
                ).update(is_active=False)

            if self._state.adding and not SiteConfiguration.objects.exists():
                self.is_active = True

            super().save(*args, **kwargs)
        cache.delete("actived_site_config")
