import re

import autoslug
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags
from django.utils.safestring import mark_safe
from django.utils.text import slugify, Truncator
from django.utils.timezone import localtime
from django.utils.timesince import timesince
from django.utils.translation import gettext_lazy as _
from functools import cached_property
from markdown import Markdown
from mdeditor.fields import MDTextField

from core.markdown.extensions import get_extensions
from .utils.unicode_slugify import unicode_slugify
from .utils.word_counter import reading_time_counter, word_counter
from .validators import validate_theme_image


CACHE_KEY = "actived_site_config"
CACHE_TIMEOUT = 60 * 60 * 24


class SiteConfiguration(models.Model):
    config_name = models.CharField("Configuration name", max_length=50, default="Default Config")
    is_active = models.BooleanField("Set as the currently active configuration", default=False)


    site_name = models.CharField(
        _("site name"), max_length=200, default="Theme Redefine"
    )
    site_subname = models.CharField(
        _("site info subtitle"),
        max_length=200,
        blank=True,
        null=True,
        default="Redefine Your Hexo Journey.",
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

    site_avatar = models.FileField(upload_to="avatar/", blank=True, null=True, validators=[validate_theme_image])
    site_logo = models.FileField(upload_to="logo/", blank=True, null=True, validators=[validate_theme_image])
    site_favicon = models.FileField(upload_to="favicon/", blank=True, null=True, validators=[validate_theme_image])

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

    swup_enabled = models.BooleanField(default=True)

    # allow social previews to differ from ordinary page metadata
    og_enabled = models.BooleanField(default=True)
    og_image = models.FileField(upload_to="opengraph/", blank=True, null=True, validators=[validate_theme_image])
    og_description = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        default="Hexo Theme Redefine, Redefine Your Hexo Journey.",
    )

    preloader_enabled = models.BooleanField(default=False)
    preloader_message = models.CharField(max_length=100, default="Loading...")

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
    light_image = models.FileField(upload_to="banner/", blank=True, null=True, validators=[validate_theme_image])
    dark_image = models.FileField(upload_to="banner/", blank=True, null=True, validators=[validate_theme_image])
    hb_title = models.CharField(max_length=100, default="Theme Redefine")
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
        choices=[
            ("auto", "Auto"),
            ("relative", "Relative"),
            ("YYYY-MM-DD", "YYYY-MM-DD"),
            ("YYYY-MM-DD HH:mm:ss", "YYYY-MM-DD HH:mm:ss"),
            ("MMM D, YYYY", "MMM D, YYYY"),
        ],
        default="auto",
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
        upload_to="recommendation/", blank=True, null=True, validators=[validate_theme_image]
    )
    recommendation_skip_dirs = models.JSONField(default=list, blank=True)

    footer_runtime_enabled = models.BooleanField(default=True)
    footer_icon = models.CharField(
        max_length=200,
        blank=True,
        default='<i class="fa-solid fa-heart fa-beat" style="--fa-animation-duration: 0.5s; color: #f54545"></i>',
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
    friends_page_columns = models.PositiveIntegerField(choices=[(2, "2 Column"), (3, "3 Column"),], default=2)
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
        """Turn an admin hex colour and percentage into safe CSS rgba()."""
        value = (hex_color or "").strip().lstrip("#")
        if len(value) == 3:
            value = "".join(char * 2 for char in value)
        if not re.fullmatch(r"[0-9a-fA-F]{6}", value):
            value = "000000"
        red, green, blue = (int(value[index:index + 2], 16) for index in (0, 2, 4))
        alpha = min(max(int(opacity or 0), 0), 100) / 100
        return f"rgba({red}, {green}, {blue}, {alpha:g})"

    @property
    def navbar_left_rgba(self):
        return self._rgba(self.navbar_lcolor, self.navbar_transparency)

    @property
    def navbar_right_rgba(self):
        return self._rgba(self.navbar_rcolor, self.navbar_transparency)

    @property
    def aplayer_tracks(self):
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
        settings = self.aplayer_config.copy() if isinstance(self.aplayer_config, dict) else {}
        settings["type"] = self.aplayer_type or settings.get("type", "fixed")
        return settings

    @property
    def aplayer_is_mini(self):
        return self.aplayer_settings["type"] == "mini"

    @property
    def comment_options(self):
        """Return the selected provider's options in the Redefine key format."""
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
        if self.comment_system == "waline":
            normalized.setdefault("lang", "zh-CN")
        return normalized

    @property
    def social_layout(self):
        """Return the utility classes used by the social-links layout."""
        if self.social_links_style == "center":
            return {
                "justify": "justify-center",
                "display": "hidden",
                "flex_dir": "flex-row"
            }
        return {
            "justify": "justify-between",
            "display": "flex",
            "flex_dir": "flex-row-reverse" if self.social_links_style == "reverse" else "flex-row"
        }

    @property
    def social_links(self):
        """Return social links belonging to this configuration."""
        return self.links.filter(link_location='social')

    @property
    def qrcode_links(self):
        """Return QR-code links belonging to this configuration."""
        return self.links.filter(link_location='qrs')
    
    @property
    def navbar_links(self):
        # return roots only; dropdown children are rendered by their parent
        return self.links.filter(link_location='navbar', parent__isnull=True).order_by('order')
    
    @property
    def sidebar_links(self):
        """Return links assigned to the sidebar."""
        return self.links.filter(link_location='sidebar').order_by('order')

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
        if self.google_analytics_enabled and not (self.google_analytics_id or "").strip():
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
            "article_categories_limit": (1, 100),
            "article_tags_limit": (1, 100),
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
            obj = cls.objects.create(
                config_name="Default Config", site_name="My Site", is_active=True
            )
        return obj

    def save(self, *args, **kwargs):
        self.full_clean(validate_constraints=False)
        with transaction.atomic():
            if self.is_active:
                SiteConfiguration.objects.filter(is_active=True).exclude(pk=self.pk).update(
                    is_active=False
                )

            if not SiteConfiguration.objects.exists():
                self.is_active = True

            super().save(*args, **kwargs)
        cache.delete('actived_site_config')
class AudioTrack(models.Model):
    name = models.CharField(max_length=150)
    artist = models.CharField(max_length=150, blank=True)
    url = models.CharField(
        max_length=500,
        blank=True,
        help_text="External URL or a path under the site media/static files.",
    )
    audio_file = models.FileField(upload_to="audio/", blank=True)
    cover = models.CharField(max_length=500, blank=True)
    cover_image = models.FileField(upload_to="audio_covers/", blank=True, null=True, validators=[validate_theme_image])
    lrc = models.TextField(blank=True)
    theme = models.CharField(max_length=20, blank=True)
    enabled = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("order", "id")
        verbose_name = "Audio track"
        verbose_name_plural = "Audio tracks"

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if not self.url and not self.audio_file:
            raise ValidationError("Provide an audio URL or upload an audio file.")


class BookmarkCategory(models.Model):
    config = models.ForeignKey(
        SiteConfiguration,
        on_delete=models.CASCADE,
        related_name="bookmark_categories",
    )
    name = models.CharField(max_length=100)
    icon = models.CharField(max_length=100, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("order", "id")
        verbose_name = "Bookmark category"
        verbose_name_plural = "Bookmark categories"

    def __str__(self):
        return self.name


class Bookmark(models.Model):
    category = models.ForeignKey(
        BookmarkCategory,
        on_delete=models.CASCADE,
        related_name="items",
    )
    name = models.CharField(max_length=100)
    link = models.URLField()
    image = models.URLField(blank=True)
    description = models.CharField(max_length=255, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("order", "id")
        verbose_name = "Bookmark"
        verbose_name_plural = "Bookmarks"

    def __str__(self):
        return self.name


class Essay(models.Model):
    config = models.ForeignKey(
        SiteConfiguration,
        on_delete=models.CASCADE,
        related_name="essays",
    )
    content = models.TextField()
    published = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Essay"
        verbose_name_plural = "Essays"

    def __str__(self):
        return self.content[:60]


class MasonryImage(models.Model):
    config = models.ForeignKey(
        SiteConfiguration,
        on_delete=models.CASCADE,
        related_name="masonry_images",
    )
    image = models.URLField()
    title = models.CharField(max_length=150, blank=True)
    description = models.CharField(max_length=255, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("order", "id")
        verbose_name = "Masonry image"
        verbose_name_plural = "Masonry images"

    def __str__(self):
        return self.title or self.image


class FriendCategory(models.Model):
    name = models.CharField(max_length=100)
    has_thumbnail = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("order", "id")
        verbose_name = "Friend category"
        verbose_name_plural = "Friend categories"

    def __str__(self):
        return self.name


class FriendLink(models.Model):
    category = models.ForeignKey(
        FriendCategory,
        on_delete=models.CASCADE,
        related_name="links",
    )
    name = models.CharField(max_length=100)
    link = models.URLField()
    avatar = models.URLField(blank=True)
    thumbnail = models.URLField(blank=True)
    description = models.CharField(max_length=255, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("order", "id")
        verbose_name = "Friend link"
        verbose_name_plural = "Friend links"

    def __str__(self):
        return self.name


class MenuLink(models.Model):
    LOCATION_CHOICES = [
        ('navbar', '顶部导航栏'),
        ('sidebar', '侧边栏菜单'),
        ('social', '首页右下角社交链接'),
        ('qrs', '社交二维码卡片'),
    ]
    
    active_namespace = models.CharField(max_length=100, blank=True)
    
    config = models.ForeignKey(SiteConfiguration, on_delete=models.CASCADE, related_name='links')
    link_location = models.CharField('部署位置', max_length=20, choices=LOCATION_CHOICES)
    name = models.CharField('显示名称', max_length=50, help_text="例如：GitHub, Bilibili, Wechat，填fa-开头为fontawesome，填http或/开头是图片")
    url = models.CharField('链接地址/路径', max_length=255, help_text="外部链接填 http，内部路径填 /")
    icon = models.CharField('图标类名', max_length=100, blank=True, help_text="FontAwesome 类名，例如：fa-solid fa-house 或 fa-brands fa-github")

    # allow nesting only where the navbar can render a dropdown
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='submenus', verbose_name="父级菜单")
    order = models.PositiveIntegerField('排序权重', default=0, help_text="数字越小越靠前")
    
    
    @property
    def inferred_namespace(self):
        if self.active_namespace:
            return self.active_namespace
        
        if self.url == '/':
            return 'index'

        # reduce detail URLs such as /tags/name to their top-level section
        if self.url and self.url.startswith("/"):
            return self.url.strip("/").split("/")[0]

        return None


    def is_active(self, request):
        match = request.resolver_match
        if not match:
            return False

        # use the resolved namespace first; it survives URL-prefix changes
        if self.inferred_namespace and match.app_name:
            return match.app_name == self.inferred_namespace

        # project-level routes may have no app namespace, so use the view name as fallback
        if self.inferred_namespace and match.view_name:
            return match.view_name.startswith(self.inferred_namespace)

        return False

    
    @property
    def has_submenus(self):
        """Return whether this navigation item has children."""
        return self.submenus.exists()
    
    @property
    def link_type(self):
        """Classify the link for social-link rendering."""
        name = self.name.lower()
        
        if name == "email":
            return "email"
        elif name.startswith("fa-"):
            return "fa"
        elif name.startswith("/") or name.startswith("http"):
            return "img"
        else:
            return "fa-default"
    @property
    def href(self):
        """Return the final href, including the mailto scheme when needed."""
        if self.url:
            if self.link_type == "email":
                return f"mailto:{self.url}"
            return self.url
        if self.has_submenus:
            return "#"
        return "#"

    @property
    def social_icon_class(self):
        """Return the Font Awesome class used by social links."""
        if self.link_type == "fa-default":
            return f"fa-{self.name}"
        return self.name

    @property
    def qr_type(self):
        """Classify a QR-code entry as an icon, image, or brand."""
        key = self.name
        if "fa-" in key:
            return "fa"
        elif key.startswith("/") or key.startswith("http"):
            return "img"
        else:
            return "brand"
    @property
    def qr_img(self):
        """Return the QR image URL."""
        return self.url
    @property
    def qr_icon_class(self):
        """Return the icon class for a brand QR entry."""
        if self.qr_type == "brand":
            return f"fa-{self.name}"
        return self.name
    
    @property
    def user_icon(self):
        """Return the explicit icon or infer one from the link name."""
        if self.icon:
            return self.icon
        
        name_lower = self.name.lower()
        if name_lower.startswith("fa-"):
            return name_lower
        
        return f"fa-solid fa-{name_lower}"


    class Meta:
        verbose_name = "Integrated link"
        verbose_name_plural = verbose_name
        ordering = ['order']
    
    def clean(self):
        # only the navbar renders nested links
        if self.parent and self.link_location != 'navbar':
            raise ValidationError({
                'parent': f"位置为 '{self.get_link_location_display()}' 的链接不允许设置父级菜单。"
            })
        
        # a child in another location would never appear under its parent
        if self.parent and self.parent.link_location != self.link_location:
            raise ValidationError("子菜单的位置必须与父级菜单一致。")
        
        # only navbar and sidebar templates read this icon field
        if self.icon and self.link_location not in ['navbar', 'sidebar']:
            raise ValidationError({
                'icon': f"只有位置为 '顶部导航栏' 或 '侧边栏菜单' 时才允许填写图标。当前位置 '{self.get_link_location_display()}' 请保持此项为空，若需要font awesome，请在名称一栏中输入。"
            })
            
        if self.parent and self.parent_id == self.id:
            raise ValidationError({'parent': "父级菜单不能是菜单本身。"})
        
        if self.parent and self.icon:
            raise ValidationError({
                'icon': f"链接 '{self.name}' 是子菜单，子菜单不允许设置图标。"
            })
    
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[{self.get_link_location_display()}] {self.name}"
    
class Font(models.Model):
    FONT_TYPE_CHOICES = [
        ('code_block', 'Code Block'),
        ('home_banner', 'Home Banner'),
        ('global', 'Global'),
        ('chinese', 'Chinese'),
        ('english', 'English'),
        ('title', 'Title'),
    ]

    config = models.ForeignKey(SiteConfiguration, on_delete=models.CASCADE, related_name='fonts')
    type = models.CharField(max_length=20, choices=FONT_TYPE_CHOICES)
    enabled = models.BooleanField(default=False)
    family = models.CharField(max_length=100, blank=True)
    url = models.URLField(blank=True)

    class Meta:
        verbose_name = "Font"
        verbose_name_plural = "Fonts"

    def __str__(self):
        return f"{self.get_type_display()} ({'enabled' if self.enabled else 'disabled'})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        cache.delete(CACHE_KEY)

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        cache.delete(CACHE_KEY)



class Category(models.Model):
    name = models.CharField(_("name"), max_length=100, unique=True)
    slug = models.SlugField(_("slug"), max_length=100, unique=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
        verbose_name=_("parent category"),
    )

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if not self.parent_id:
            return
        if self.pk and self.parent_id == self.pk:
            raise ValidationError({"parent": "A category cannot be its own parent."})

        ancestor = self.parent
        visited = set()
        while ancestor is not None:
            if ancestor.pk in visited or (self.pk and ancestor.pk == self.pk):
                raise ValidationError({"parent": "Category parents cannot form a cycle."})
            visited.add(ancestor.pk)
            ancestor = ancestor.parent


class Tag(models.Model):
    name = models.CharField(_("name"), max_length=100, unique=True)
    slug = models.SlugField(_("slug"), max_length=100, unique=True)

    def __str__(self):
        return self.name


class ArticleQuerySet(models.QuerySet):
    def published(self):
        return (
            self.filter(is_published=True, created_at__lte=timezone.now())
            .order_by('-sticky', '-created_at')
            .prefetch_related('category', 'tags')
        )

class ArticleModel(models.Model):
    objects = ArticleQuerySet.as_manager()
    
    title = models.CharField(_("title"), max_length=200)
    writer = models.CharField(_("writer"), max_length=100, blank=True)
    slug = autoslug.AutoSlugField(_("slug"), populate_from='title', max_length=255, unique=True, blank=True, always_update=False, slugify=unicode_slugify)
    excerpt = models.TextField(_("excerpt"), max_length=500, blank=True)
    content = MDTextField(_("content"))

    is_published = models.BooleanField(_("is published"), default=False, db_index=True)
    expires_at = models.DateTimeField(_("expires at"), blank=True, null=True)
    created_at = models.DateTimeField(_("created at"), default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    sticky = models.PositiveIntegerField(default=0)
    writer_avatar = models.FileField(upload_to="writer_avatar/", blank=True, null=True, validators=[validate_theme_image])
    thumbnail = models.FileField(upload_to="thumbnails/", blank=True, null=True, validators=[validate_theme_image])
    cover = models.FileField(upload_to="cover/", blank=True, null=True, validators=[validate_theme_image])
    banner = models.FileField(upload_to="banner/", blank=True, null=True, validators=[validate_theme_image])
    category = models.ManyToManyField("Category", blank=True, verbose_name=_("category"))
    tags = models.ManyToManyField("Tag", blank=True, verbose_name=_("tags"))

    # allow a per-article license override without changing the site default
    copyright_override_enabled = models.BooleanField(default=False)
    copyright_override_type = models.CharField(
        max_length=50,
        choices=SiteConfiguration.COPYRIGHT_CHOICES,
        blank=True,
        null=True,
    )
    # override the site comment switch only for this article
    show_comment = models.BooleanField(default=True)
    
    # cache counters; archive and footer pages should not render every article body
    word_counter = models.PositiveIntegerField(default=0, editable=False)
    reading_time = models.PositiveIntegerField(default=0, editable=False)

    @cached_property
    def meta(self):
        site = SiteConfiguration.get_config()

        date_format = getattr(site, 'article_dateformat', 'auto')
        local_time = localtime(self.created_at)
        if date_format in ('auto', 'relative'):
            home_date = f"{timesince(local_time)} ago"
        else:
            # these values come from the old Moment.js setting
            python_formats = {
                'YYYY-MM-DD': '%Y-%m-%d',
                'YYYY-MM-DD HH:mm:ss': '%Y-%m-%d %H:%M:%S',
                'MMM D, YYYY': '%b %d, %Y',
            }
            home_date = local_time.strftime(
                python_formats.get(date_format, '%Y-%m-%d')
            )
            if date_format == 'MMM D, YYYY':
                home_date = home_date.replace(' 0', ' ')

        categories_display = []
        if getattr(site, 'article_categories_enabled', True):
            previous_parent_id = object()
            # all() reuses the prefetch cache when the queryset has one
            category_limit = getattr(site, 'article_categories_limit', 0)
            for index, cat in enumerate(self.category.all()):
                if category_limit and index >= category_limit:
                    break
                parent_id = getattr(cat, 'parent_id', None)
                categories_display.append({
                    'name': cat.name,
                    'url': reverse('categories_detail', args=[cat.slug]),
                    'new_parent': previous_parent_id != parent_id
                })
                previous_parent_id = parent_id

        tags_display = []
        if getattr(site, 'article_tags_enabled', True):
            tags_limit = getattr(site, 'article_tags_limit', 0)
            for i, tag in enumerate(self.tags.all()):
                if tags_limit and i >= tags_limit:
                    break
                tags_display.append({
                    'name': tag.name,
                    'url': reverse('tags_detail', args=[tag.slug]),
                    'first': i == 0
                })

        return {
            'title': self.title,
            'path': reverse('article', args=[self.slug]),
            'home_date': home_date,
            'categories': categories_display,
            'tags': tags_display,
            'thumbnail_url': self.thumbnail_url,
            'auto_excerpt': self.auto_excerpt,
            'sticky': self.sticky,
        }

    
    @cached_property
    def _rendered(self):
        site = SiteConfiguration.get_config()
        max_depth = getattr(site, 'toc_max_depth', 3) 
        toc_depth_range = f"1-{max_depth}"

        md = Markdown(
            extensions = get_extensions(site),
            extension_configs={
                "markdown.extensions.toc": {
                    "permalink": "",
                    "toc_depth": toc_depth_range,
                    "slugify": slugify, 
                }
            },
        )
        html = md.convert(self.content)
        toc_html = re.sub(r'<a(\s+)', r'<a class="nav-link"\1', md.toc)
        # Redefine styles an ordered TOC tree; Python Markdown emits an unordered one
        toc_html = re.sub(r'^\s*<div class="toc">\s*', '', toc_html)
        toc_html = re.sub(r'\s*</div>\s*$', '', toc_html)
        toc_html = toc_html.replace('<li>', '<li class="nav-item">')
        toc_html = re.sub(r'<(?:ul|ol)>', '<ol class="nav">', toc_html, count=1)
        toc_html = re.sub(r'<(?:ul|ol)>', '<ol class="nav-child">', toc_html)
        toc_html = re.sub(r'</(?:ul|ol)>', '</ol>', toc_html)
        toc_html = re.sub(
            r'(<a class="nav-link" href="[^"]+">)(.*?)(</a>)',
            r'\1<span class="nav-text">\2</span>\3',
            toc_html,
            flags=re.DOTALL,
        )
        return {
            "content": mark_safe(html),
            "toc": mark_safe(toc_html),
        }
    @property
    def html_content(self):
        return self._rendered["content"]
    @property
    def toc(self):
        return self._rendered["toc"]

    @cached_property
    def licence_label(self):
        if self.copyright_override_enabled and self.copyright_override_type:
            licence_type = self.copyright_override_type
        else:
            licence_type = SiteConfiguration.get_config().copyright_type

        licence_map = {
            'all_rights_reserved': '<span>All rights reserved</span>',
            'cc_by': '<a class="license" href="https://creativecommons.org/licenses/by/4.0">CC BY 4.0</a>',
            'cc_by_sa': '<a class="license" href="https://creativecommons.org/licenses/by-sa/4.0">CC BY-SA 4.0</a>',
            'cc_by_nc': '<a class="license" href="https://creativecommons.org/licenses/by-nc/4.0">CC BY-NC 4.0</a>',
            'cc_by_nd': '<a class="license" href="https://creativecommons.org/licenses/by-nd/4.0">CC BY-ND 4.0</a>',
            'cc_by_nc_sa': '<a class="license" href="https://creativecommons.org/licenses/by-nc-sa/4.0">CC BY-NC-SA 4.0</a>',
            'public_domain': '<span>Public domain</span>',
        }


        return mark_safe(licence_map.get(licence_type, f"License: {licence_type}"))

    @property
    def thumbnail_url(self):
        for img in (self.thumbnail, self.cover, self.banner):
            if img:
                return img.url
        return None

    @cached_property
    def auto_excerpt(self):
        if self.excerpt:
            return self.excerpt
        site = SiteConfiguration.get_config()
        length = getattr(site, "article_excerpt_length", 200)
        # code blocks make poor excerpts and may include copied toolbar text
        content = re.sub(
            r"<pre\b[^>]*>.*?</pre\s*>|<code\b[^>]*>.*?</code\s*>",
            "",
            self.html_content,
            flags=re.IGNORECASE | re.DOTALL,
        )
        return Truncator(strip_tags(content)).chars(length)


    def get_absolute_url(self):
        return reverse('article', kwargs={'slug': self.slug})

    def save(self, *args, **kwargs):
        self.word_counter = word_counter(self.content or "")
        self.reading_time = reading_time_counter(self.content or "")
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "content" in update_fields:
            kwargs["update_fields"] = set(update_fields) | {"word_counter", "reading_time"}
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class Comment(models.Model):
    """A comment attached to an article, with optional nested replies."""

    article = models.ForeignKey(
        ArticleModel,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    author = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="blog_comments",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="replies",
    )
    nickname = models.CharField(max_length=80, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)
    content = models.TextField(max_length=5000)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    browser = models.CharField(max_length=120, blank=True)
    operating_system = models.CharField(max_length=120, blank=True)
    is_sticky = models.BooleanField(default=False, db_index=True)
    is_approved = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("article",),
                condition=Q(is_sticky=True),
                name="unique_sticky_comment_per_article",
            ),
        ]

    @property
    def display_name(self):
        if self.author_id:
            return self.author.get_full_name() or self.author.username
        return self.nickname or "Anonymous"

    @property
    def avatar_url(self):
        if self.author_id and hasattr(self.author, "profile"):
            avatar = getattr(self.author.profile, "avatar", None)
            if avatar:
                return avatar.url
        return ""

    @property
    def like_count(self):
        return self.likes.count()

    def clean(self):
        if self.parent_id:
            if self.parent_id == self.pk:
                raise ValidationError("A comment cannot reply to itself.")
            if self.parent.article_id != self.article_id:
                raise ValidationError("A reply must belong to the same article.")
            ancestor = self.parent
            visited = set()
            while ancestor is not None:
                if ancestor.pk in visited or (self.pk and ancestor.pk == self.pk):
                    raise ValidationError("Comment replies cannot form a cycle.")
                visited.add(ancestor.pk)
                ancestor = ancestor.parent
        if self.author_id:
            self.nickname = ""
            self.email = ""
        elif not self.nickname:
            raise ValidationError({"nickname": "Guest comments require a nickname."})

    def __str__(self):
        return f"{self.display_name}: {self.content[:40]}"


class CommentImage(models.Model):
    """An uploaded comment image, retained only while a comment references it."""

    uploader = models.ForeignKey(
        "auth.User",
        on_delete=models.CASCADE,
        related_name="comment_images",
    )
    comment = models.ForeignKey(
        Comment,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="images",
    )
    image = models.ImageField(upload_to="comment-images/")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return self.image.name


class CommentLike(models.Model):
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name="likes")
    user = models.ForeignKey("auth.User", on_delete=models.CASCADE, related_name="comment_likes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("comment", "user"), name="unique_comment_like"),
        ]


class CommentNotification(models.Model):
    REPLY = "reply"
    LIKE = "like"
    KIND_CHOICES = ((REPLY, "Reply"), (LIKE, "Like"))

    recipient = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, related_name="comment_notifications"
    )
    actor = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="comment_actions"
    )
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)


class CommentBadge(models.Model):
    """A configurable label that can be granted to registered commenters."""

    config = models.ForeignKey(
        SiteConfiguration, on_delete=models.CASCADE, related_name="comment_badges"
    )
    name = models.CharField(max_length=40)
    # an empty value inherits the active theme colour
    color = models.CharField(max_length=32, default="", blank=True)
    admin_only = models.BooleanField(default=True)
    enabled = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("order", "id")
        constraints = [
            models.UniqueConstraint(fields=("config", "name"), name="unique_comment_badge_name"),
        ]

    def __str__(self):
        return self.name


class CommentBadgeAssignment(models.Model):
    user = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, related_name="comment_badges"
    )
    badge = models.ForeignKey(
        CommentBadge, on_delete=models.CASCADE, related_name="assignments"
    )
    # an empty value inherits the badge colour
    color_override = models.CharField(max_length=32, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("badge__order", "badge_id")
        constraints = [
            models.UniqueConstraint(fields=("user", "badge"), name="unique_comment_badge_assignment"),
        ]


class CommentEmojiPack(models.Model):
    config = models.ForeignKey(
        SiteConfiguration, on_delete=models.CASCADE, related_name="comment_emoji_packs"
    )
    name = models.CharField(max_length=80)
    base_url = models.URLField(blank=True)
    enabled = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("order", "id")

    def __str__(self):
        return self.name


class CommentEmoji(models.Model):
    pack = models.ForeignKey(CommentEmojiPack, on_delete=models.CASCADE, related_name="items")
    name = models.CharField(max_length=80)
    image_url = models.URLField()
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("order", "id")

    def __str__(self):
        return f"{self.pack.name}: {self.name}"


class CommentGifSource(models.Model):
    config = models.ForeignKey(
        SiteConfiguration, on_delete=models.CASCADE, related_name="comment_gif_sources"
    )
    name = models.CharField(max_length=80)
    endpoint = models.URLField()
    enabled = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("order", "id")

    def __str__(self):
        return self.name


class TrafficModel(models.Model):
    path = models.CharField(max_length=255, db_index=True)
    ip = models.GenericIPAddressField(db_index=True)
    user_agent = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['ip', 'path', 'created_at']),
        ]
        ordering = ['-created_at']
        verbose_name = '访问记录'
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.ip} -> {self.path}"
