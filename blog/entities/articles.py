import hashlib
import json
import re
from functools import cached_property

import autoslug
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.dateformat import format as django_date_format
from django.utils.html import format_html, strip_tags
from django.utils.safestring import mark_safe
from django.utils.text import slugify, Truncator
from django.utils.timezone import localtime
from django.utils.timesince import timesince
from django.utils.translation import gettext, gettext_lazy as _
from markdown import Markdown
from mdeditor.fields import MDTextField

from core.markdown.extensions import get_extensions
from blog.services.html_safety import clean_html
from blog.utils.unicode_slugify import unicode_slugify
from blog.utils.word_counter import reading_time_counter, word_counter
from blog.validators import validate_theme_image

from .accounts import UserProfile
from .site import SiteConfiguration


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
                raise ValidationError(
                    {"parent": "Category parents cannot form a cycle."}
                )
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
            .order_by("-sticky", "-created_at")
            .prefetch_related("category", "tags")
        )


class ArticleModel(models.Model):
    objects = ArticleQuerySet.as_manager()

    title = models.CharField(_("title"), max_length=200)
    writer = models.CharField(_("writer"), max_length=100, blank=True)
    slug = autoslug.AutoSlugField(
        _("slug"),
        populate_from="title",
        max_length=255,
        unique=True,
        blank=True,
        always_update=False,
        slugify=unicode_slugify,
    )
    excerpt = models.TextField(_("excerpt"), max_length=500, blank=True)
    content = MDTextField(_("content"))

    is_published = models.BooleanField(_("is published"), default=False, db_index=True)
    expires_at = models.DateTimeField(_("expires at"), blank=True, null=True)
    created_at = models.DateTimeField(
        _("created at"), default=timezone.now, db_index=True
    )
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    sticky = models.PositiveIntegerField(default=0)
    writer_avatar = models.FileField(
        upload_to="writer_avatar/",
        blank=True,
        null=True,
        validators=[validate_theme_image],
    )
    thumbnail = models.FileField(
        upload_to="thumbnails/",
        blank=True,
        null=True,
        validators=[validate_theme_image],
    )
    cover = models.FileField(
        upload_to="cover/",
        blank=True,
        null=True,
        validators=[validate_theme_image],
    )
    banner = models.FileField(
        upload_to="banner/",
        blank=True,
        null=True,
        validators=[validate_theme_image],
    )
    category = models.ManyToManyField(
        "Category", blank=True, verbose_name=_("category")
    )
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
    show_reaction = models.BooleanField(default=True)

    # cache counters; archive and footer pages should not render every article body
    word_counter = models.PositiveIntegerField(default=0, editable=False)
    reading_time = models.PositiveIntegerField(default=0, editable=False)
    view_count = models.PositiveBigIntegerField(default=0, editable=False)

    def _categories_meta(self, site, *, limited):
        categories_display = []
        # These are home-card switches. Article pages always show their full
        # metadata, as Redefine 2.8.5 does.
        if limited and not getattr(site, "article_categories_enabled", True):
            return categories_display

        previous_parent_id = object()
        category_limit = getattr(site, "article_categories_limit", 0) if limited else 0
        for index, cat in enumerate(self.category.all()):
            if category_limit and index >= category_limit:
                break
            parent_id = getattr(cat, "parent_id", None)
            categories_display.append(
                {
                    "name": cat.name,
                    "url": reverse("categories_detail", args=[cat.slug]),
                    "new_parent": previous_parent_id != parent_id,
                }
            )
            previous_parent_id = parent_id
        return categories_display

    def _tags_meta(self, site, *, limited):
        tags_display = []
        if limited and not getattr(site, "article_tags_enabled", True):
            return tags_display

        tags_limit = getattr(site, "article_tags_limit", 0) if limited else 0
        for index, tag in enumerate(self.tags.all()):
            if tags_limit and index >= tags_limit:
                break
            tags_display.append(
                {
                    "name": tag.name,
                    "url": reverse("tags_detail", args=[tag.slug]),
                    "first": index == 0,
                }
            )
        return tags_display

    @cached_property
    def meta(self):
        site = SiteConfiguration.get_config()

        date_format = getattr(site, "article_dateformat", "auto")
        local_time = localtime(self.created_at)
        if date_format == "relative":
            home_date = gettext("%(elapsed)s ago") % {"elapsed": timesince(local_time)}
        else:
            home_date = self._format_moment(
                local_time,
                "YYYY-MM-DD" if date_format == "auto" else date_format,
            )

        return {
            "title": self.title,
            "path": reverse("article", args=[self.slug]),
            "home_date": home_date,
            "categories": self._categories_meta(site, limited=True),
            "tags": self._tags_meta(site, limited=True),
            "thumbnail_url": self.thumbnail_url,
            "auto_excerpt": self.auto_excerpt,
            "sticky": self.sticky,
        }

    @staticmethod
    def _format_moment(value, pattern):
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
            "categories": self._categories_meta(site, limited=False),
            "tags": self._tags_meta(site, limited=False),
        }

    @cached_property
    def _rendered(self):
        site = SiteConfiguration.get_config()
        max_depth = getattr(site, "toc_max_depth", 3)
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
        cache_key = f"article-markdown:v2:{self.pk or 'new'}:{digest}"
        cached = cache.get(cache_key)
        if cached is not None:
            return {
                "content": mark_safe(cached["content"]),
                "toc": mark_safe(cached["toc"]),
            }

        md = Markdown(
            extensions=get_extensions(site),
            extension_configs={
                "markdown.extensions.toc": {
                    "permalink": "",
                    "toc_depth": toc_depth_range,
                    "slugify": slugify,
                }
            },
        )
        html = clean_html(md.convert(self.content))
        toc_html = re.sub(r"<a(\s+)", r'<a class="nav-link"\1', md.toc)
        # Redefine styles an ordered TOC tree; Python Markdown emits an unordered one
        toc_html = re.sub(r'^\s*<div class="toc">\s*', "", toc_html)
        toc_html = re.sub(r"\s*</div>\s*$", "", toc_html)
        toc_html = toc_html.replace("<li>", '<li class="nav-item">')
        toc_html = re.sub(r"<(?:ul|ol)>", '<ol class="nav">', toc_html, count=1)
        toc_html = re.sub(r"<(?:ul|ol)>", '<ol class="nav-child">', toc_html)
        toc_html = re.sub(r"</(?:ul|ol)>", "</ol>", toc_html)
        toc_html = re.sub(
            r'(<a class="nav-link" href="[^"]+">)(.*?)(</a>)',
            r'\1<span class="nav-text">\2</span>\3',
            toc_html,
            flags=re.DOTALL,
        )
        toc_html = clean_html(toc_html)
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
                if owner_profile and owner_profile.display_name.strip()
                else SiteConfiguration.get_config().site_author
            )
            return format_html(
                gettext("All Rights Reserved &#169; {author}"), author=author
            )
        if licence_type == "public_domain":
            return mark_safe(gettext("This work is in the public domain."))

        licence_map = {
            "cc_by": ("https://creativecommons.org/licenses/by/4.0", "CC BY 4.0"),
            "cc_by_sa": (
                "https://creativecommons.org/licenses/by-sa/4.0",
                "CC BY-SA 4.0",
            ),
            "cc_by_nc": (
                "https://creativecommons.org/licenses/by-nc/4.0",
                "CC BY-NC 4.0",
            ),
            "cc_by_nd": (
                "https://creativecommons.org/licenses/by-nd/4.0",
                "CC BY-ND 4.0",
            ),
            "cc_by_nc_sa": (
                "https://creativecommons.org/licenses/by-nc-sa/4.0",
                "CC BY-NC-SA 4.0",
            ),
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
    def _format_datetime(value):
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
        return self._format_datetime(self.created_at)

    @property
    def updated_at_display(self):
        return self._format_datetime(self.updated_at)

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
            return mark_safe(clean_html(md.convert(self.excerpt)))
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
        return reverse("article", kwargs={"slug": self.slug})

    def save(self, *args, **kwargs):
        self.word_counter = word_counter(self.content or "")
        self.reading_time = reading_time_counter(self.content or "")
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "content" in update_fields:
            kwargs["update_fields"] = set(update_fields) | {
                "word_counter",
                "reading_time",
            }
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
