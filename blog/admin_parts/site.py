import json
import re

from adminsortable2.admin import SortableAdminBase, SortableTabularInline
from django.conf import settings
from django.contrib import admin
from django.contrib import messages
from django import forms
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from ..admin_labels import (
    SITE_CONFIGURATION_CHOICE_LABELS,
    SITE_CONFIGURATION_FIELD_LABELS,
    SITE_CONFIGURATION_HELP_TEXTS,
)
from ..models import (
    CommentEmoji,
    CommentEmojiPack,
    CommentGifSource,
    Font,
    MenuLink,
    MenuLinkTranslation,
    SiteConfiguration,
)

admin.site.site_header = "Django Redefine Administration"
admin.site.site_title = "Django Redefine Admin"
admin.site.index_title = _("Administration")
admin.site.site_url = "/"


class SiteConfigurationForm(forms.ModelForm):
    """Expose provider options as regular fields while storing Redefine JSON."""

    PROVIDER_FIELDS = {
        "waline": (
            "serverUrl",
            "lang",
            "emoji",
            "reaction",
            "recaptchaV3Key",
            "turnstileKey",
        ),
        "gitalk": ("clientID", "clientSecret", "owner", "repo", "proxy"),
        "twikoo": ("version", "server_url", "region"),
        "giscus": (
            "repo",
            "repo_id",
            "category",
            "category_id",
            "mapping",
            "lang",
            "strict",
            "reactions_enabled",
            "emit_metadata",
            "input_position",
            "loading",
        ),
    }
    REQUIRED_PROVIDER_FIELDS = {
        "waline": ("server_url",),
        "gitalk": ("client_id", "client_secret", "owner", "repo"),
        "twikoo": ("server_url",),
        "giscus": ("repo", "repo_id", "category", "category_id"),
    }

    waline_server_url = forms.URLField(
        required=False,
        label=_("Server URL"),
        help_text=_("Use the Waline service root, not its /ui administration path."),
    )
    waline_lang = forms.CharField(required=False, initial="zh-CN", label=_("Language"))
    waline_emoji = forms.CharField(
        required=False,
        widget=forms.Textarea,
        label=_("Emoji URLs (JSON array)"),
    )
    waline_reaction = forms.CharField(
        required=False,
        widget=forms.Textarea,
        label=_("Reactions (JSON array)"),
    )
    waline_recaptcha_v3_key = forms.CharField(
        required=False, label=_("reCAPTCHA v3 site key")
    )
    waline_turnstile_key = forms.CharField(
        required=False, label=_("Turnstile site key")
    )
    gitalk_client_id = forms.CharField(required=False, label=_("Client ID"))
    gitalk_client_secret = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=True),
        label=_("Client secret"),
    )
    gitalk_owner = forms.CharField(required=False, label=_("Repository owner"))
    gitalk_repo = forms.CharField(required=False, label=_("Repository name"))
    gitalk_proxy = forms.URLField(required=False, label=_("OAuth proxy URL"))
    twikoo_version = forms.CharField(
        required=False, initial="1.6.44", label=_("Client version")
    )
    twikoo_server_url = forms.URLField(required=False, label=_("Server URL"))
    twikoo_region = forms.CharField(required=False, label=_("Deployment region"))
    giscus_repo = forms.CharField(required=False, label=_("Repository"))
    giscus_repo_id = forms.CharField(required=False, label=_("Repository ID"))
    giscus_category = forms.CharField(required=False, label=_("Discussion category"))
    giscus_category_id = forms.CharField(
        required=False, label=_("Discussion category ID")
    )
    giscus_mapping = forms.ChoiceField(
        required=False,
        choices=[
            ("pathname", _("Pathname")),
            ("url", _("URL")),
            ("title", _("Page title")),
        ],
        label=_("Page mapping"),
    )
    giscus_lang = forms.CharField(required=False, initial="en", label=_("Language"))
    giscus_strict = forms.ChoiceField(
        required=False,
        choices=[("0", _("Disabled")), ("1", _("Enabled"))],
        label=_("Use strict matching"),
    )
    giscus_reactions_enabled = forms.ChoiceField(
        required=False,
        choices=[("0", _("Disabled")), ("1", _("Enabled"))],
        label=_("Enable reactions"),
    )
    giscus_emit_metadata = forms.ChoiceField(
        required=False,
        choices=[("0", _("Disabled")), ("1", _("Enabled"))],
        label=_("Send discussion metadata"),
    )
    giscus_input_position = forms.ChoiceField(
        required=False,
        choices=[("bottom", _("Bottom")), ("top", _("Top"))],
        label=_("Comment box position"),
    )
    giscus_loading = forms.ChoiceField(
        required=False,
        choices=[("lazy", _("Lazy")), ("eager", _("Immediate"))],
        label=_("Loading strategy"),
    )

    class Meta:
        model = SiteConfiguration
        exclude = ("comment_config",)

    @staticmethod
    def _field_name(provider, key):
        for source, target in {
            "serverUrl": "server_url",
            "clientID": "client_id",
            "clientSecret": "client_secret",
            "recaptchaV3Key": "recaptcha_v3_key",
            "turnstileKey": "turnstile_key",
        }.items():
            key = key.replace(source, target)
        return f"{provider}_{key}"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, label in SITE_CONFIGURATION_FIELD_LABELS.items():
            field = self.fields.get(field_name)
            if field is not None:
                field.label = label
        for field_name, help_text in SITE_CONFIGURATION_HELP_TEXTS.items():
            field = self.fields.get(field_name)
            if field is not None:
                field.help_text = help_text
        for field_name, translated_labels in SITE_CONFIGURATION_CHOICE_LABELS.items():
            field = self.fields.get(field_name)
            if field is None:
                continue
            field.choices = [
                (value, translated_labels.get(value, label))
                for value, label in field.choices
            ]
        raw_config = self.instance.comment_config if self.instance.pk else {}
        raw_config = raw_config if isinstance(raw_config, dict) else {}
        for provider, fields in self.PROVIDER_FIELDS.items():
            options = raw_config.get(provider, {})
            if provider == self.instance.comment_system and not isinstance(
                options, dict
            ):
                options = self.instance.comment_options
            options = options if isinstance(options, dict) else {}
            for field in fields:
                form_field = self._field_name(provider, field)
                if form_field in self.fields:
                    value = options.get(field, "")
                    if field in ("emoji", "reaction") and value:
                        value = json.dumps(value, ensure_ascii=False)
                    self.fields[form_field].initial = value

        for name in (
            "colour_primary",
            "navbar_lcolor",
            "navbar_rcolor",
            "hb_light_text",
            "hb_dark_text",
        ):
            if name in self.fields:
                self.fields[name].widget.attrs["type"] = "color"
                value = self.initial.get(name)
                if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{3}", value):
                    self.initial[name] = "#" + "".join(
                        character * 2 for character in value[1:]
                    )

    def clean(self):
        cleaned = super().clean()
        provider = cleaned.get("comment_system")
        if cleaned.get("comment_enabled") and not provider:
            self.add_error(
                "comment_system",
                _("Choose a comment provider when comments are enabled."),
            )

        if cleaned.get("comment_enabled"):
            for suffix in self.REQUIRED_PROVIDER_FIELDS.get(provider, ()):
                field_name = f"{provider}_{suffix}"
                if not cleaned.get(field_name):
                    self.add_error(
                        field_name,
                        _("This field is required for the selected comment provider."),
                    )

        for field_name in ("waline_emoji", "waline_reaction"):
            value = cleaned.get(field_name)
            if not value:
                cleaned[field_name] = []
                continue
            try:
                parsed = json.loads(value) if isinstance(value, str) else value
            except json.JSONDecodeError:
                self.add_error(field_name, _("Enter a valid JSON array."))
                continue
            if not isinstance(parsed, list):
                self.add_error(field_name, _("This value must be a JSON array."))
                continue
            cleaned[field_name] = parsed

        schema = {
            "subtitle_text": list,
            "author_label_list": list,
            "recommendation_skip_dirs": list,
            "aplayer_config": dict,
        }
        for field_name, expected_type in schema.items():
            value = cleaned.get(field_name)
            if value in (None, ""):
                continue
            if not isinstance(value, expected_type):
                expected = _("array") if expected_type is list else _("object")
                self.add_error(
                    field_name,
                    _("This value must be a JSON %(type)s.") % {"type": expected},
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
            value = cleaned.get(field_name)
            if value is not None and not minimum <= value <= maximum:
                self.add_error(
                    field_name,
                    _("Enter a value between %(minimum)s and %(maximum)s.")
                    % {"minimum": minimum, "maximum": maximum},
                )

        for field_name in (
            "colour_primary",
            "navbar_lcolor",
            "navbar_rcolor",
            "hb_light_text",
            "hb_dark_text",
        ):
            value = cleaned.get(field_name)
            if value and not re.fullmatch(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?", value):
                self.add_error(
                    field_name,
                    _("Enter a colour in #RGB or #RRGGBB format."),
                )

        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        provider = self.cleaned_data.get("comment_system")
        options = {}
        for key in self.PROVIDER_FIELDS.get(provider, ()):
            form_field = self._field_name(provider, key)
            value = self.cleaned_data.get(form_field)
            if value not in (None, ""):
                options[key] = value
        stored = (
            instance.comment_config.copy()
            if isinstance(instance.comment_config, dict)
            else {}
        )
        if provider:
            stored[provider] = options
        instance.comment_config = stored
        if commit:
            instance.save()
        return instance


class MenuLinkInline(SortableTabularInline):
    model = MenuLink
    extra = 1
    classes = ("collapse",)
    show_change_link = True
    fields = ("link_location", "name", "url", "icon", "parent")
    ordering = ("order",)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "parent":
            object_id = request.resolver_match.kwargs.get("object_id")
            if object_id:
                kwargs["queryset"] = MenuLink.objects.exclude(id=object_id)
            else:
                kwargs["queryset"] = MenuLink.objects.all()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class MenuLinkTranslationForm(forms.ModelForm):
    class Meta:
        model = MenuLinkTranslation
        fields = ("language_code", "name")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["language_code"].label = _("Language")
        self.fields["name"].label = _("Display name")
        self.fields["language_code"].widget = forms.Select(
            choices=[
                (code, label) for code, label in settings.LANGUAGES if code != "en"
            ]
        )


class MenuLinkTranslationInline(admin.TabularInline):
    model = MenuLinkTranslation
    form = MenuLinkTranslationForm
    extra = 0
    fields = ("language_code", "name")
    verbose_name = _("Language-specific label")
    verbose_name_plural = _("Custom navigation labels")


class FontInline(admin.TabularInline):
    model = Font
    extra = 0
    can_delete = True
    fields = ("type", "enabled", "family", "url")


class CommentEmojiInline(admin.TabularInline):
    model = CommentEmoji
    extra = 1
    fields = ("name", "image_url", "order")


class CommentEmojiPackInline(admin.TabularInline):
    model = CommentEmojiPack
    extra = 0
    fields = ("name", "base_url", "enabled", "order")


class CommentGifSourceInline(admin.TabularInline):
    model = CommentGifSource
    extra = 0
    fields = ("name", "endpoint", "enabled", "order")


@admin.register(SiteConfiguration)
class SiteConfigurationAdmin(SortableAdminBase, admin.ModelAdmin):
    form = SiteConfigurationForm

    class Media:
        js = ("js/admin/comment-config.js",)

    save_as = True
    save_on_top = True
    list_display = (
        "config_name",
        "active_state",
        "site_name",
        "site_author",
        "comment_system",
        "colour_default_mode",
    )
    list_filter = ("is_active", "comment_system")
    search_fields = (
        "config_name",
        "site_name",
        "site_subname",
        "site_author",
        "site_description",
        "site_keywords",
    )
    ordering = ("-is_active", "config_name")
    list_per_page = 30
    actions = ("activate_configuration",)

    def changelist_view(self, request, extra_context=None):
        context = {"title": _("Site configurations")}
        context.update(extra_context or {})
        return super().changelist_view(request, extra_context=context)

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        context = {
            "title": (
                _("Edit site configuration")
                if object_id
                else _("Add site configuration")
            )
        }
        context.update(extra_context or {})
        return super().changeform_view(
            request,
            object_id=object_id,
            form_url=form_url,
            extra_context=context,
        )

    # emoji packs and GIF sources are shared instead of being copied with each configuration
    inlines = [MenuLinkInline, FontInline]

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        field = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "colour_primary":
            field.help_text = _(
                "Used by links, buttons, pagination, and status indicators. "
                "Configure the navigation gradient separately below."
            )
        elif db_field.name in {"navbar_lcolor", "navbar_rcolor"}:
            field.help_text = _(
                "The navigation gradient is independent of the primary colour."
            )
        if db_field.name == "aplayer_config":
            field.help_text = _("Optional JSON object for advanced APlayer settings.")
        return field

    def save_model(self, request, obj, form, change):
        # ModelForm has already run model and uniqueness validation. Avoid
        # validating this very large configuration a second time on every
        # admin save; direct model saves still keep full validation enabled.
        obj.save(validate=False)

    fieldsets = (
        (
            _("Configuration"),
            {
                "fields": ("config_name", "is_active"),
            },
        ),
        (
            _("Site identity"),
            {
                "fields": (
                    "site_name",
                    ("site_subname", "site_author"),
                    "site_description",
                    "site_keywords",
                    ("site_avatar", "site_logo", "site_favicon"),
                )
            },
        ),
        (
            _("Colours and preloader"),
            {
                "classes": ("collapse",),
                "fields": (
                    ("colour_primary", "colour_default_mode"),
                    ("effect_hover_shadow", "effect_hover_scale"),
                    ("preloader_enabled", "preloader_message"),
                ),
            },
        ),
        (
            _("Font Awesome"),
            {
                "classes": ("collapse",),
                "fields": (
                    ("fontawesome_thin", "fontawesome_light"),
                    ("fontawesome_duotone", "fontawesome_sharp_solid"),
                ),
            },
        ),
        (
            _("Home banner"),
            {
                "classes": ("collapse",),
                "fields": (
                    "homebanner_enabled",
                    ("homebanner_style", "hb_title"),
                    ("light_image", "dark_image"),
                    ("hb_light_text", "hb_dark_text"),
                    ("text_title_size", "text_subtitle_size", "text_line_height"),
                    ("social_links_enabled", "social_links_style"),
                ),
            },
        ),
        (
            _("Home subtitle"),
            {
                "classes": ("collapse",),
                "fields": (
                    "subtitle_enabled",
                    "subtitle_text",
                    ("st_hitokoto_enable", "st_hitokoto_show_author"),
                    "st_hitokoto_api",
                    ("st_typing_speed", "st_backing_speed"),
                    ("st_starting_delay", "st_backing_delay"),
                    ("subtitle_loop", "st_smart_backspace"),
                ),
            },
        ),
        (
            _("Navigation and sidebar"),
            {
                "classes": ("collapse",),
                "fields": (
                    ("navbar_autohide", "navbar_search_enabled"),
                    ("navbar_lcolor", "navbar_rcolor", "navbar_transparency"),
                    ("sidebar_enabled", "sidebar_position", "sidebar_on_mobile"),
                    ("sidebar_firstitem", "sidebar_announcement"),
                    ("sidetools_gear_rotation", "sidetools_auto_expand"),
                ),
            },
        ),
        (
            _("Comments"),
            {
                "classes": ("collapse",),
                "description": _(
                    "Choose a provider and complete its settings when comments are enabled."
                ),
                "fields": (
                    ("comment_enabled", "comment_system"),
                    ("comment_require_login", "comment_allow_guest"),
                    ("comment_auto_approve", "comment_allow_likes"),
                    (
                        "comment_email_notifications",
                        "comment_emoji_enabled",
                        "comment_gif_enabled",
                    ),
                    (
                        "comment_registration_enabled",
                        "comment_require_email_verification",
                    ),
                    "comment_profile_review_enabled",
                    ("waline_server_url", "waline_lang"),
                    "waline_emoji",
                    "waline_reaction",
                    ("waline_recaptcha_v3_key", "waline_turnstile_key"),
                    ("gitalk_client_id", "gitalk_client_secret"),
                    ("gitalk_owner", "gitalk_repo"),
                    "gitalk_proxy",
                    ("twikoo_version", "twikoo_region"),
                    "twikoo_server_url",
                    ("giscus_repo", "giscus_repo_id"),
                    ("giscus_category", "giscus_category_id"),
                    ("giscus_mapping", "giscus_lang"),
                    (
                        "giscus_strict",
                        "giscus_reactions_enabled",
                        "giscus_emit_metadata",
                    ),
                    ("giscus_input_position", "giscus_loading"),
                ),
            },
        ),
        (
            _("Article display"),
            {
                "classes": ("collapse",),
                "fields": (
                    "article_reaction_enabled",
                    ("article_dateformat", "article_excerpt_length"),
                    ("article_categories_enabled", "article_categories_limit"),
                    ("counter_enabled", "show_word_counter", "show_reading_time"),
                    ("article_tags_enabled", "article_tags_limit"),
                    ("article_image_alignment", "article_image_description"),
                    ("title_alignment", "hyperlink_icon", "delete_mask"),
                    ("article_lazyload", "article_pangu_js"),
                    ("copyright_enabled", "copyright_type"),
                    ("author_label_enabled", "author_label_auto"),
                    "author_label_list",
                ),
            },
        ),
        (
            _("Code blocks and table of contents"),
            {
                "classes": ("collapse",),
                "fields": (
                    ("code_block_copy", "code_block_style"),
                    ("codeblock_light", "codeblock_dark"),
                    ("toc_enabled", "toc_max_depth", "toc_has_number"),
                    ("toc_expand", "toc_init_open"),
                ),
            },
        ),
        (
            _("Extensions"),
            {
                "classes": ("collapse",),
                "fields": (
                    ("swup_enabled", "mermaid_enabled", "rssfeed_enabled"),
                    "rssfeed_url",
                    ("reading_bar_enabled", "reading_bar_percentage"),
                    ("recommendation_enabled", "recommendation_limit"),
                    ("recommendation_mobile_limit", "recommendation_skip_dirs"),
                    "recommendation_title",
                    "recommendation_placeholder",
                ),
            },
        ),
        (
            _("APlayer"),
            {
                "classes": ("collapse",),
                "description": (
                    _(
                        "Enable the player here and manage songs on the Audio tracks page. "
                        "Use the JSON field only for advanced APlayer options."
                    )
                ),
                "fields": (
                    ("aplayer_enabled", "aplayer_type"),
                    "aplayer_config",
                ),
            },
        ),
        (
            _("SEO, analytics, and footer"),
            {
                "classes": ("collapse",),
                "fields": (
                    ("og_enabled", "og_image"),
                    "og_description",
                    ("google_analytics_enabled", "google_analytics_id"),
                    ("footer_runtime_enabled", "footer_sitestart"),
                    "footer_icon",
                    ("footer_statistics", "show_icp"),
                    (
                        "website_counter_enabled",
                        "website_counter_site_pv",
                        "website_counter_site_uv",
                        "website_counter_post_pv",
                    ),
                    ("icp_number", "icp_url"),
                    "footer_content",
                ),
            },
        ),
        (
            _("Advanced settings"),
            {
                "classes": ("collapse",),
                "fields": (
                    "inject_enabled",
                    "inject_header",
                    "inject_footer",
                ),
            },
        ),
    )

    @admin.display(description=_("Status"), ordering="is_active")
    def active_state(self, obj):
        label = _("Active") if obj.is_active else _("Inactive")
        css_class = (
            "admin-status admin-status-active" if obj.is_active else "admin-status"
        )
        return format_html('<span class="{}">{}</span>', css_class, label)

    @admin.action(description=_("Use selected configuration"))
    def activate_configuration(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(
                request, _("Select exactly one configuration."), level=messages.ERROR
            )
            return
        selected = queryset.first()
        selected.is_active = True
        selected.save(update_fields=("is_active",))
        self.message_user(
            request,
            _("The selected configuration is now active."),
            level=messages.SUCCESS,
        )

    def has_delete_permission(self, request, obj=None):
        """Control whether the delete button is available."""
        if SiteConfiguration.objects.count() <= 1:
            return False
        if obj and obj.is_active:
            return False
        return True

    def delete_queryset(self, request, queryset):
        """Prevent unsafe bulk deletion of configurations."""
        if (
            queryset.filter(is_active=True).exists()
            or queryset.count() == SiteConfiguration.objects.count()
        ):
            self.message_user(
                request,
                _(
                    "The active configuration cannot be deleted, "
                    "and at least one configuration must remain."
                ),
                level=messages.ERROR,
            )
            return
        queryset.delete()


@admin.register(MenuLink)
class MenuLinkAdmin(admin.ModelAdmin):
    list_display = ("name", "link_location", "config", "parent", "url", "order")
    list_filter = ("link_location", "config")
    search_fields = (
        "name",
        "translations__name",
        "url",
        "icon",
        "active_namespace",
        "config__config_name",
    )
    autocomplete_fields = ("parent",)
    list_select_related = ("config", "parent")
    ordering = ("config", "link_location", "order", "id")
    inlines = (MenuLinkTranslationInline,)


@admin.register(Font)
class FontAdmin(admin.ModelAdmin):
    list_display = ("family", "type", "config", "enabled", "url")
    list_filter = ("enabled", "type", "config")
    search_fields = ("family", "url", "config__config_name")
    list_select_related = ("config",)
    ordering = ("config", "type", "id")
