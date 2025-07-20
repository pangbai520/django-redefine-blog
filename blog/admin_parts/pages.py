from django import forms
from django.conf import settings
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from blog.models import SiteConfiguration, StandalonePage, StandalonePageTranslation

from .forms import UniqueLanguageInlineFormSet


class StandalonePageTranslationWidget(forms.Textarea):
    """Editor.md source field that can be initialized after an inline is added."""

    class Media:
        js = ("js/admin/standalone-page-translations.js",)

    def __init__(self, attrs=None):
        default_attrs = {
            "class": "standalone-page-markdown-source",
            "data-library-path": f"{settings.STATIC_URL}mdeditor/js/lib/",
            "data-upload-url": settings.MDEDITOR_CONFIGS["default"]["upload_image_url"],
        }

        if attrs:
            default_attrs.update(attrs)

        super().__init__(default_attrs)


class StandalonePageTranslationForm(forms.ModelForm):
    # MDTextFormField always replaces Meta.widgets with MDEditorWidget, so the
    # field must be declared explicitly for a formset-safe widget.
    content = forms.CharField(
        label=_("translated page content"),
        required=False,
        widget=StandalonePageTranslationWidget(),
    )

    class Meta:
        model = StandalonePageTranslation
        fields = ("language_code", "title", "content")


class StandalonePageTranslationInline(admin.StackedInline):
    model = StandalonePageTranslation
    form = StandalonePageTranslationForm
    formset = UniqueLanguageInlineFormSet
    extra = 0


@admin.register(StandalonePage)
class StandalonePageAdmin(admin.ModelAdmin):
    exclude = ("config",)
    list_display = (
        "title",
        "page_type",
        "slug",
        "enabled",
        "include_in_sitemap",
        "updated_at",
    )

    list_filter = ("enabled", "page_type", "include_in_sitemap")
    search_fields = ("title", "slug", "content")
    prepopulated_fields = {"slug": ("title",)}
    inlines = (StandalonePageTranslationInline,)

    def get_fieldsets(self, request, obj=None):
        display_fields = ["show_title", "include_in_sitemap"]
        if obj is None or obj.page_type == StandalonePage.CUSTOM:
            display_fields.insert(1, "comments_enabled")
        if obj is not None and obj.page_type == StandalonePage.FRIENDS:
            display_fields.append("friends_columns")
        if obj is not None and obj.page_type == StandalonePage.TAGS:
            display_fields.append("tags_style")
        return (
            (
                None,
                {
                    "fields": (
                        ("page_type", "enabled"),
                        ("title", "slug"),
                        "content",
                    )
                },
            ),
            (_("Display and indexing"), {"fields": (tuple(display_fields),)}),
        )

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ()
        return ("page_type",)

    def get_prepopulated_fields(self, request, obj=None):
        if obj is not None and obj.page_type != StandalonePage.CUSTOM:
            return {}

        return super().get_prepopulated_fields(request, obj)

    def save_model(self, request, obj, form, change):
        if not obj.config_id:
            obj.config = SiteConfiguration.get_config()

        super().save_model(request, obj, form, change)
