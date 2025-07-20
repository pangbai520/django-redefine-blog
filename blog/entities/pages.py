from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils.translation import get_language, gettext_lazy as _
from mdeditor.fields import MDTextField

from blog.utils.unicode_slugify import unicode_slugify


class StandalonePage(models.Model):
    CUSTOM = "custom"
    ARCHIVES = "archives"
    CATEGORIES = "categories"
    TAGS = "tags"
    FRIENDS = "friends"
    BOOKMARKS = "bookmarks"
    ESSAYS = "essays"
    MASONRY = "masonry"

    PAGE_TYPES = (
        (CUSTOM, _("Custom page")),
        (ARCHIVES, _("Archives")),
        (CATEGORIES, _("Categories")),
        (TAGS, _("Tags")),
        (FRIENDS, _("Friends")),
        (BOOKMARKS, _("Bookmarks")),
        (ESSAYS, _("Essays")),
        (MASONRY, _("Masonry")),
    )
    BUILTIN_DEFAULTS = {
        ARCHIVES: {"title": "Archives", "slug": "archives", "enabled": True},
        CATEGORIES: {
            "title": "Categories",
            "slug": "categories",
            "enabled": True,
        },
        TAGS: {"title": "Tags", "slug": "tags", "enabled": True},
        FRIENDS: {"title": "Friends", "slug": "friends", "enabled": True},
        BOOKMARKS: {
            "title": "Bookmarks",
            "slug": "bookmarks",
            "enabled": False,
        },
        ESSAYS: {"title": "Essays", "slug": "essays", "enabled": False},
        MASONRY: {"title": "Masonry", "slug": "masonry", "enabled": False},
    }
    RESERVED_SLUGS = {
        "admin",
        "api",
        "article",
        "comments",
        "feed",
        "health",
        "i18n",
        "robots",
        "rss",
        "search",
        "sitemap",
    }

    config = models.ForeignKey(
        "blog.SiteConfiguration",
        on_delete=models.CASCADE,
        related_name="standalone_pages",
    )
    page_type = models.CharField(
        _("page type"),
        max_length=20,
        choices=PAGE_TYPES,
        default=CUSTOM,
    )
    title = models.CharField(_("title"), max_length=200)
    slug = models.SlugField(
        _("URL slug"),
        max_length=200,
        allow_unicode=True,
        help_text=_("The page is available at /this-slug/."),
    )
    content = MDTextField(
        _("page content"),
        blank=True,
        help_text=_("Markdown shown after the built-in page content."),
    )
    enabled = models.BooleanField(_("show this page"), default=True)
    show_title = models.BooleanField(_("show page title"), default=True)
    comments_enabled = models.BooleanField(
        _("enable comments"),
        default=False,
        help_text=_("Show the configured comment system on this custom page."),
    )
    include_in_sitemap = models.BooleanField(_("include in sitemap"), default=True)
    friends_columns = models.PositiveSmallIntegerField(
        _("friend-link columns"),
        choices=((2, "2"), (3, "3")),
        default=2,
    )
    tags_style = models.CharField(
        _("tags style"),
        max_length=20,
        choices=(("blur", _("Blur")), ("cloud", _("Cloud"))),
        default="blur",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("page_type", "title", "id")
        verbose_name = _("page")
        verbose_name_plural = _("pages")
        constraints = [
            models.UniqueConstraint(
                fields=("config", "slug"),
                name="unique_standalone_page_slug",
            ),
            models.UniqueConstraint(
                fields=("config", "page_type"),
                condition=~Q(page_type="custom"),
                name="unique_builtin_page_type",
            ),
        ]

    def clean(self):
        super().clean()
        slug = (self.slug or "").strip()
        builtin = {item["slug"] for item in self.BUILTIN_DEFAULTS.values()}
        own_default = self.BUILTIN_DEFAULTS.get(self.page_type, {}).get("slug")
        if slug in self.RESERVED_SLUGS or (
            slug in builtin and slug != own_default
        ):
            raise ValidationError(
                {"slug": _("This URL is reserved for a built-in page.")}
            )

    def save(self, *args, **kwargs):
        if not self.slug:
            if self.page_type == self.CUSTOM:
                self.slug = unicode_slugify(self.title)
            else:
                self.slug = self.BUILTIN_DEFAULTS[self.page_type]["slug"]
        super().save(*args, **kwargs)

    @classmethod
    def _reserved_slugs(cls):
        builtin = {item["slug"] for item in cls.BUILTIN_DEFAULTS.values()}
        return builtin | cls.RESERVED_SLUGS

    def _localized_value(self, field, language_code=None):
        if not self.pk:
            return self._default_value(field)

        language = (language_code or get_language() or "").replace("_", "-")
        language = language.lower()
        translations = list(self.translations.all())
        for candidate in (language, language.split("-", 1)[0]):
            for translation in translations:
                code = translation.language_code.replace("_", "-").lower()
                if code == candidate:
                    value = getattr(translation, field, "")
                    if value:
                        return value
        return self._default_value(field)

    def _default_value(self, field):
        value = getattr(self, field)
        if field != "title" or self.page_type == self.CUSTOM:
            return value

        default = self.BUILTIN_DEFAULTS[self.page_type]["title"]
        if value != default:
            return value
        return str(dict(self.PAGE_TYPES)[self.page_type])

    def localized_title(self, language_code=None):
        return self._localized_value("title", language_code)

    def localized_content(self, language_code=None):
        return self._localized_value("content", language_code)

    def get_absolute_url(self):
        return reverse("standalone_page", kwargs={"slug": self.slug})

    def __str__(self):
        return self.title


class StandalonePageTranslation(models.Model):
    page = models.ForeignKey(
        StandalonePage,
        on_delete=models.CASCADE,
        related_name="translations",
    )
    language_code = models.CharField(
        _("language code"),
        max_length=20,
        choices=settings.LANGUAGES,
    )
    title = models.CharField(
        _("translated page title"),
        max_length=200,
        blank=True,
    )
    content = MDTextField(_("translated page content"), blank=True)

    class Meta:
        ordering = ("language_code", "id")
        verbose_name = _("page translation")
        verbose_name_plural = _("page translations")
        constraints = [
            models.UniqueConstraint(
                fields=("page", "language_code"),
                name="unique_standalone_page_translation_language",
            )
        ]

    def __str__(self):
        return f"{self.page.title} ({self.language_code})"
