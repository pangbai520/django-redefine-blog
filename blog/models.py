import hashlib
import json
import re
import uuid
from pathlib import Path

import autoslug
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import models, transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.dateformat import format as django_date_format
from django.utils.html import format_html, strip_tags
from django.utils.safestring import mark_safe
from django.utils.text import slugify, Truncator
from django.utils.timezone import localtime
from django.utils.timesince import timesince
from django.utils.translation import get_language, gettext, gettext_lazy as _
from functools import cached_property
from markdown import Markdown
from mdeditor.fields import MDTextField

from core.markdown.extensions import get_extensions
from .utils.unicode_slugify import unicode_slugify
from .utils.word_counter import reading_time_counter, word_counter
from .validators import validate_profile_avatar, validate_theme_image


CACHE_KEY = "actived_site_config"
CACHE_TIMEOUT = 60 * 60 * 24


def user_avatar_upload_to(instance, filename):
    suffix = Path(filename).suffix.lower()
    return f"user-avatars/{instance.user_id}/{uuid.uuid4().hex}{suffix}"


class SiteConfiguration(models.Model):
    config_name = models.CharField("Configuration name", max_length=50, default="Default Config")
    is_active = models.BooleanField("Set as the currently active configuration", default=False)


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
    website_counter_enabled = models.BooleanField(default=True)
    website_counter_site_pv = models.BooleanField(default=True)
    website_counter_site_uv = models.BooleanField(default=True)
    website_counter_post_pv = models.BooleanField(default=True)

    swup_enabled = models.BooleanField(default=True)

    # allow social previews to differ from ordinary page metadata
    og_enabled = models.BooleanField(default=True)
    og_image = models.FileField(upload_to="opengraph/", blank=True, null=True, validators=[validate_theme_image])
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
    light_image = models.FileField(upload_to="banner/", blank=True, null=True, validators=[validate_theme_image])
    dark_image = models.FileField(upload_to="banner/", blank=True, null=True, validators=[validate_theme_image])
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
    friends_enabled = models.BooleanField(default=True)
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
        """Reproduce Redefine's two-digit hexadecimal alpha setting."""
        value = (hex_color or "").strip().lstrip("#")
        if len(value) == 3:
            value = "".join(char * 2 for char in value)
        if not re.fullmatch(r"[0-9a-fA-F]{6}", value):
            value = "000000"
        red, green, blue = (int(value[index:index + 2], 16) for index in (0, 2, 4))
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
        return self.links.filter(
            link_location='navbar', parent__isnull=True
        ).prefetch_related(
            'translations', 'submenus__translations'
        ).order_by('order')
    
    @property
    def sidebar_links(self):
        """Return links assigned to the sidebar."""
        return self.links.filter(
            link_location='sidebar'
        ).prefetch_related('translations').order_by('order')

    @property
    def mobile_sidebar_links(self):
        """Avoid repeating links already present in the mobile navbar."""
        navbar = self.links.filter(
            link_location='navbar', parent__isnull=True
        )
        navbar_urls = set(navbar.values_list('url', flat=True))
        navbar_names = {
            name.casefold() for name in navbar.values_list('name', flat=True)
        }
        return [
            link for link in self.sidebar_links
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
            obj = cls.objects.create(
                config_name="Default Config", is_active=True
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
    name = models.CharField(
        '默认显示名称',
        max_length=50,
        help_text=(
            "默认名称（通常填写英文）。About、Archives 等标准名称会自动翻译；"
            "自定义名称可在保存后进入此链接配置各语言翻译。"
        ),
    )
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

    @staticmethod
    def _normalized_language_code(language_code):
        code = (language_code or '').strip().lower().replace('_', '-')
        aliases = {
            'zh-cn': 'zh-hans',
            'zh-sg': 'zh-hans',
            'zh-hant': 'zh-tw',
            'zh-mo': 'zh-hk',
        }
        return aliases.get(code, code)

    def resolve_localized_name(self, language_code=None):
        """Return ``(label, is_explicit_translation)`` for the active language."""
        code = self._normalized_language_code(language_code or get_language())
        if not code or code == 'en' or code.startswith('en-'):
            return self.name, False

        candidates = [code]
        base_code = code.split('-', 1)[0]
        if base_code in {'es', 'fr', 'ja'} and base_code not in candidates:
            candidates.append(base_code)

        prefetched = getattr(self, '_prefetched_objects_cache', {}).get('translations')
        if prefetched is None:
            translations = self.translations.filter(language_code__in=candidates)
        else:
            translations = prefetched

        translations_by_code = {
            item.language_code: item.name
            for item in translations
            if item.language_code in candidates
        }
        for candidate in candidates:
            if candidate in translations_by_code:
                return translations_by_code[candidate], True

        return self.name, False

    
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


class MenuLinkTranslation(models.Model):
    menu_link = models.ForeignKey(
        MenuLink,
        on_delete=models.CASCADE,
        related_name='translations',
        verbose_name='菜单链接',
    )
    language_code = models.CharField('语言代码', max_length=16)
    name = models.CharField('显示名称', max_length=50)

    class Meta:
        ordering = ('language_code',)
        constraints = (
            models.UniqueConstraint(
                fields=('menu_link', 'language_code'),
                name='unique_menu_link_language',
            ),
        )
        verbose_name = '菜单链接翻译'
        verbose_name_plural = '菜单链接翻译'

    def __str__(self):
        language_name = dict(settings.LANGUAGES).get(
            self.language_code, self.language_code
        )
        return f"{self.menu_link.name} ({language_name})"

    def clean(self):
        supported_languages = {
            code for code, _name in settings.LANGUAGES if code != 'en'
        }
        if self.language_code not in supported_languages:
            raise ValidationError({
                'language_code': '请选择网站当前支持的非英语语言。'
            })
    
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

    def _categories_meta(self, site, *, limited):
        categories_display = []
        # These are home-card switches. Article pages always show their full
        # metadata, as Redefine 2.8.5 does.
        if limited and not getattr(site, 'article_categories_enabled', True):
            return categories_display

        previous_parent_id = object()
        category_limit = getattr(site, 'article_categories_limit', 0) if limited else 0
        for index, cat in enumerate(self.category.all()):
            if category_limit and index >= category_limit:
                break
            parent_id = getattr(cat, 'parent_id', None)
            categories_display.append({
                'name': cat.name,
                'url': reverse('categories_detail', args=[cat.slug]),
                'new_parent': previous_parent_id != parent_id,
            })
            previous_parent_id = parent_id
        return categories_display

    def _tags_meta(self, site, *, limited):
        tags_display = []
        if limited and not getattr(site, 'article_tags_enabled', True):
            return tags_display

        tags_limit = getattr(site, 'article_tags_limit', 0) if limited else 0
        for index, tag in enumerate(self.tags.all()):
            if tags_limit and index >= tags_limit:
                break
            tags_display.append({
                'name': tag.name,
                'url': reverse('tags_detail', args=[tag.slug]),
                'first': index == 0,
            })
        return tags_display

    @cached_property
    def meta(self):
        site = SiteConfiguration.get_config()

        date_format = getattr(site, 'article_dateformat', 'auto')
        local_time = localtime(self.created_at)
        if date_format == 'relative':
            home_date = gettext("%(elapsed)s ago") % {
                "elapsed": timesince(local_time)
            }
        else:
            home_date = self._format_moment_datetime(
                local_time,
                'YYYY-MM-DD' if date_format == 'auto' else date_format,
            )

        return {
            'title': self.title,
            'path': reverse('article', args=[self.slug]),
            'home_date': home_date,
            'categories': self._categories_meta(site, limited=True),
            'tags': self._tags_meta(site, limited=True),
            'thumbnail_url': self.thumbnail_url,
            'auto_excerpt': self.auto_excerpt,
            'sticky': self.sticky,
        }

    @staticmethod
    def _format_moment_datetime(value, pattern):
        """Render the Moment.js tokens accepted by Redefine's date option."""
        hour12 = value.hour % 12 or 12
        offset = value.strftime("%z")
        tokens = {
            "YYYY": f"{value.year:04d}",
            "YY": f"{value.year % 100:02d}",
            "MMMM": django_date_format(value, "F"),
            "MMM": django_date_format(value, "M"),
            "MM": f"{value.month:02d}",
            "M": str(value.month),
            "DD": f"{value.day:02d}",
            "D": str(value.day),
            "dddd": django_date_format(value, "l"),
            "ddd": django_date_format(value, "D"),
            "HH": f"{value.hour:02d}",
            "H": str(value.hour),
            "hh": f"{hour12:02d}",
            "h": str(hour12),
            "mm": f"{value.minute:02d}",
            "m": str(value.minute),
            "ss": f"{value.second:02d}",
            "s": str(value.second),
            "A": "AM" if value.hour < 12 else "PM",
            "a": "am" if value.hour < 12 else "pm",
            "ZZ": offset,
            "Z": f"{offset[:3]}:{offset[3:]}" if offset else "",
        }
        token_pattern = re.compile(
            r"\[[^\]]*\]|YYYY|MMMM|dddd|MMM|ddd|YY|MM|DD|HH|hh|mm|ss|ZZ|M|D|H|h|m|s|A|a|Z"
        )

        def replace_token(match):
            token = match.group(0)
            if token.startswith("["):
                return token[1:-1]
            return tokens[token]

        return token_pattern.sub(replace_token, pattern or "YYYY-MM-DD")

    @cached_property
    def detail_meta(self):
        """Article-page metadata is complete; home limits belong to cards only."""
        site = SiteConfiguration.get_config()
        return {
            'categories': self._categories_meta(site, limited=False),
            'tags': self._tags_meta(site, limited=False),
        }

    
    @cached_property
    def _rendered(self):
        site = SiteConfiguration.get_config()
        max_depth = getattr(site, 'toc_max_depth', 3) 
        toc_depth_range = f"1-{max_depth}"

        render_options = {
            "toc_max_depth": max_depth,
            "hyperlink_icon": site.hyperlink_icon,
            "article_image_description": site.article_image_description,
            "article_lazyload": site.article_lazyload,
            "mermaid_enabled": site.mermaid_enabled,
            "delete_mask": site.delete_mask,
        }
        digest = hashlib.sha256(
            (self.content + json.dumps(render_options, sort_keys=True)).encode("utf-8")
        ).hexdigest()
        cache_key = f"article-markdown:v1:{self.pk or 'new'}:{digest}"
        cached = cache.get(cache_key)
        if cached is not None:
            return {
                "content": mark_safe(cached["content"]),
                "toc": mark_safe(cached["toc"]),
            }

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
        rendered = {"content": html, "toc": toc_html}
        cache.set(
            cache_key,
            rendered,
            getattr(settings, "MARKDOWN_CACHE_TIMEOUT", 7 * 24 * 60 * 60),
        )
        return {
            "content": mark_safe(rendered["content"]),
            "toc": mark_safe(rendered["toc"]),
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

        if licence_type == "all_rights_reserved":
            owner_profile = (
                UserProfile.objects.filter(
                    user__is_superuser=True,
                    user__is_active=True,
                )
                .select_related("user")
                .order_by("user__date_joined", "user_id")
                .first()
            )
            author = (
                owner_profile.display_name.strip()
                if owner_profile
                and owner_profile.display_name.strip()
                else SiteConfiguration.get_config().site_author
            )
            return format_html(
                gettext("All Rights Reserved &#169; {author}"), author=author
            )
        if licence_type == "public_domain":
            return mark_safe(gettext("This work is in the public domain."))

        licence_map = {
            'cc_by': ('https://creativecommons.org/licenses/by/4.0', 'CC BY 4.0'),
            'cc_by_sa': ('https://creativecommons.org/licenses/by-sa/4.0', 'CC BY-SA 4.0'),
            'cc_by_nc': ('https://creativecommons.org/licenses/by-nc/4.0', 'CC BY-NC 4.0'),
            'cc_by_nd': ('https://creativecommons.org/licenses/by-nd/4.0', 'CC BY-ND 4.0'),
            'cc_by_nc_sa': ('https://creativecommons.org/licenses/by-nc-sa/4.0', 'CC BY-NC-SA 4.0'),
        }
        licence = licence_map.get(licence_type)
        if not licence:
            return gettext("License: %(license)s") % {"license": licence_type}
        url, label = licence
        link = format_html('<a class="license" href="{}">{}</a>', url, label)
        return format_html(
            gettext("This work is licensed under {license}."), license=link
        )

    @property
    def thumbnail_url(self):
        """Image used by home cards and recommendation tiles.

        Redefine 2.8.5 deliberately gives ``thumbnail`` first priority on
        listing pages, then falls back to ``cover`` and ``banner``.
        """
        for img in (self.thumbnail, self.cover, self.banner):
            if img:
                return img.url
        return None

    @property
    def article_cover_url(self):
        """Image used behind the title on an article page.

        This order differs from the home card in upstream Redefine: an
        explicit cover wins, followed by banner and finally thumbnail.
        """
        for img in (self.cover, self.banner, self.thumbnail):
            if img:
                return img.url
        return None

    @staticmethod
    def _format_article_datetime(value):
        if not value:
            return ""
        rendered = localtime(value).strftime("%Y-%m-%d %H:%M:%S")
        if rendered.endswith(" 00:00:00"):
            return rendered[:-9]
        if rendered.endswith(":00"):
            return rendered[:-3]
        return rendered

    @property
    def created_at_display(self):
        return self._format_article_datetime(self.created_at)

    @property
    def updated_at_display(self):
        return self._format_article_datetime(self.updated_at)

    @property
    def has_meaningful_update(self):
        """Avoid showing a duplicate update time immediately after creation."""
        if not self.updated_at or not self.created_at:
            return False
        return abs((self.updated_at - self.created_at).total_seconds()) >= 1

    @cached_property
    def auto_excerpt(self):
        if self.excerpt:
            # Redefine renders a manually supplied excerpt as Markdown.
            # Otherwise syntax such as emphasis and links leaks into the home
            # card as literal punctuation.
            site = SiteConfiguration.get_config()
            md = Markdown(
                extensions=get_extensions(site),
                extension_configs={
                    "markdown.extensions.toc": {
                        "toc_depth": f"1-{getattr(site, 'toc_max_depth', 3)}",
                        "slugify": slugify,
                    }
                },
            )
            return mark_safe(md.convert(self.excerpt))
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


class ArticleSearchDocument(models.Model):
    """A compact search projection kept separate from authored Markdown."""

    article = models.OneToOneField(
        ArticleModel,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="search_document",
    )
    title = models.CharField(max_length=200, db_index=True)
    excerpt = models.TextField(blank=True)
    content = models.TextField()
    indexed_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-article__created_at",)

    def __str__(self):
        return self.title


class UserProfile(models.Model):
    """Public-facing identity for a registered comment account."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    display_name = models.CharField(_("display name"), max_length=80, blank=True)
    avatar = models.ImageField(
        _("avatar"),
        upload_to=user_avatar_upload_to,
        blank=True,
        validators=[validate_profile_avatar],
    )
    pending_display_name = models.CharField(
        _("pending display name"), max_length=80, blank=True
    )
    pending_avatar = models.ImageField(
        _("pending avatar"),
        upload_to=user_avatar_upload_to,
        blank=True,
        validators=[validate_profile_avatar],
    )
    pending_avatar_change = models.BooleanField(default=False)
    profile_review_pending = models.BooleanField(default=False, db_index=True)
    profile_review_requested_at = models.DateTimeField(null=True, blank=True)
    pending_email = models.EmailField(_("pending email"), blank=True)
    pending_email_requested_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("user__username",)

    @property
    def resolved_display_name(self):
        return (
            self.display_name.strip()
            or self.user.get_full_name()
            or self.user.get_username()
        )

    @property
    def pending_resolved_display_name(self):
        return (
            self.pending_display_name.strip()
            or self.user.get_full_name()
            or self.user.get_username()
        )

    def stage_profile_changes(self, *, display_name, avatar=None, remove_avatar=False):
        """Store a public identity draft without changing the live profile."""
        replaced_storage = self.pending_avatar.storage if self.pending_avatar else None
        replaced_name = self.pending_avatar.name if self.pending_avatar else ""
        self.pending_display_name = display_name.strip()
        if avatar is not None:
            self.pending_avatar = avatar
            self.pending_avatar_change = True
        elif remove_avatar:
            self.pending_avatar = None
            self.pending_avatar_change = True
        elif not self.profile_review_pending:
            self.pending_avatar_change = False
        self.profile_review_pending = True
        self.profile_review_requested_at = timezone.now()
        self.save(
            update_fields=(
                "pending_display_name",
                "pending_avatar",
                "pending_avatar_change",
                "profile_review_pending",
                "profile_review_requested_at",
            )
        )
        if replaced_name and replaced_name != self.pending_avatar.name:
            transaction.on_commit(
                lambda storage=replaced_storage, name=replaced_name: storage.delete(name)
            )

    def clear_pending_profile_changes(self):
        pending_storage = self.pending_avatar.storage if self.pending_avatar else None
        pending_name = self.pending_avatar.name if self.pending_avatar else ""
        self.pending_display_name = ""
        self.pending_avatar = None
        self.pending_avatar_change = False
        self.profile_review_pending = False
        self.profile_review_requested_at = None
        self.save(
            update_fields=(
                "pending_display_name",
                "pending_avatar",
                "pending_avatar_change",
                "profile_review_pending",
                "profile_review_requested_at",
            )
        )
        if pending_name:
            transaction.on_commit(
                lambda storage=pending_storage, name=pending_name: storage.delete(name)
            )

    def approve_pending_profile_changes(self):
        """Publish the staged identity and leave unrelated account data alone."""
        if not self.profile_review_pending:
            return False

        pending_storage = self.pending_avatar.storage if self.pending_avatar else None
        pending_name = self.pending_avatar.name if self.pending_avatar else ""
        self.display_name = self.pending_display_name
        if self.pending_avatar_change:
            if self.pending_avatar:
                self.pending_avatar.open("rb")
                try:
                    copied_avatar = ContentFile(
                        self.pending_avatar.read(),
                        name=Path(self.pending_avatar.name).name,
                    )
                finally:
                    self.pending_avatar.close()
                self.avatar.save(copied_avatar.name, copied_avatar, save=False)
            else:
                self.avatar = None

        self.pending_display_name = ""
        self.pending_avatar = None
        self.pending_avatar_change = False
        self.profile_review_pending = False
        self.profile_review_requested_at = None
        self.save(
            update_fields=(
                "display_name",
                "avatar",
                "pending_display_name",
                "pending_avatar",
                "pending_avatar_change",
                "profile_review_pending",
                "profile_review_requested_at",
            )
        )
        if pending_name:
            transaction.on_commit(
                lambda storage=pending_storage, name=pending_name: storage.delete(name)
            )
        return True

    def __str__(self):
        return self.resolved_display_name


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
            profile = getattr(self.author, "profile", None)
            if profile and profile.display_name.strip():
                return profile.display_name.strip()
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

    def save(self, *args, **kwargs):
        if not self.is_sticky or not self.article_id:
            return super().save(*args, **kwargs)

        # MySQL does not create conditional unique constraints. Lock the
        # article row so concurrent saves still agree on a single pinned
        # comment, while PostgreSQL and SQLite retain the database constraint
        # as an additional safeguard.
        with transaction.atomic():
            ArticleModel.objects.select_for_update().filter(pk=self.article_id).exists()
            type(self).objects.filter(
                article_id=self.article_id,
                is_sticky=True,
            ).exclude(pk=self.pk).update(is_sticky=False)
            return super().save(*args, **kwargs)

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
