from django import forms
from django.contrib import admin
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _, ngettext

from blog.models import (
    Comment,
    CommentBadge,
    CommentBadgeAssignment,
    CommentBadgeTranslation,
    CommentEmoji,
    CommentEmojiPack,
    CommentGifSource,
    CommentLike,
    CommentNotification,
    SiteConfiguration,
)

from .forms import UniqueLanguageInlineFormSet


class CommentEmojiInline(admin.TabularInline):
    model = CommentEmoji
    extra = 0
    fields = ("name", "image_url", "reaction_order", "order")


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = (
        "display_name",
        "comment_target",
        "is_approved",
        "is_sticky",
        "ip_address",
        "browser",
        "operating_system",
        "created_at",
        "admin_like_count",
    )
    list_filter = ("is_approved", "is_sticky", "created_at")
    search_fields = (
        "content",
        "nickname",
        "email",
        "author__username",
        "article__title",
        "page__title",
    )
    autocomplete_fields = ("author", "parent")
    raw_id_fields = ("article", "page")
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "created_at"
    list_select_related = ("article", "page", "author", "parent")
    list_per_page = 50
    actions = ("approve_comments", "hold_comments", "pin_comments", "unpin_comments")

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(_admin_like_count=models.Count("likes"))
        )

    @admin.display(description=_("Page"), ordering="article__title")
    def comment_target(self, obj):
        return obj.article or obj.page

    @admin.display(description=_("Likes"), ordering="_admin_like_count")
    def admin_like_count(self, obj):
        return obj._admin_like_count

    @admin.action(description=_("Approve selected comments"))
    def approve_comments(self, request, queryset):
        queryset.update(is_approved=True)
        self.message_user(request, _("Selected comments were approved."))

    @admin.action(description=_("Return selected comments to review"))
    def hold_comments(self, request, queryset):
        queryset.update(is_approved=False)
        self.message_user(request, _("Selected comments were returned to review."))

    @admin.action(description=_("Pin selected comment"))
    def pin_comments(self, request, queryset):
        selected = list(
            queryset.order_by("article_id", "page_id", "-created_at", "-pk")
        )
        by_target = {}
        for comment in selected:
            if comment.article_id:
                key = ("article", comment.article_id)
            else:
                key = ("page", comment.page_id)
            by_target.setdefault(key, comment)
        with transaction.atomic():
            article_ids = [pk for kind, pk in by_target if kind == "article"]
            page_ids = [pk for kind, pk in by_target if kind == "page"]
            Comment.objects.filter(
                models.Q(article_id__in=article_ids) | models.Q(page_id__in=page_ids)
            ).update(is_sticky=False)
            selected_ids = [item.pk for item in by_target.values()]
            pinned = Comment.objects.filter(pk__in=selected_ids).update(is_sticky=True)
        skipped = len(selected) - pinned
        message = ngettext(
            "Pinned %(count)d comment.",
            "Pinned %(count)d comments.",
            pinned,
        ) % {"count": pinned}
        if skipped:
            message += " " + ngettext(
                "Skipped %(count)d duplicate selection because only one "
                "comment can be pinned per page.",
                "Skipped %(count)d duplicate selections because only one "
                "comment can be pinned per page.",
                skipped,
            ) % {"count": skipped}
        self.message_user(request, message)

    @admin.action(description=_("Unpin selected comments"))
    def unpin_comments(self, request, queryset):
        queryset.update(is_sticky=False)
        self.message_user(request, _("Selected comments were unpinned."))


class CommentBadgeTranslationFormSet(UniqueLanguageInlineFormSet):
    def save_new(self, form, commit=True):
        language_code = form.cleaned_data.get("language_code")
        existing = CommentBadgeTranslation.objects.filter(
            badge=self.instance,
            language_code=language_code,
        ).first()
        if existing is None:
            return super().save_new(form, commit=commit)
        existing.name = form.cleaned_data.get("name", existing.name)
        if commit:
            existing.save(update_fields=("name",))
        return existing


class CommentBadgeTranslationInline(admin.TabularInline):
    model = CommentBadgeTranslation
    formset = CommentBadgeTranslationFormSet
    extra = 0


@admin.register(CommentBadge)
class CommentBadgeAdmin(admin.ModelAdmin):
    class form(forms.ModelForm):
        color = forms.CharField(
            required=False,
            label=_("Colour"),
            widget=forms.TextInput(attrs={"type": "color", "class": "vTextField"}),
        )
        inherit_theme = forms.BooleanField(
            required=False,
            label=_("Follow primary colour"),
            help_text=_("Disable this to choose a custom badge colour."),
        )

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.initial["inherit_theme"] = not bool(
                self.instance and self.instance.color
            )

        def clean(self):
            cleaned = super().clean()
            if cleaned.get("inherit_theme"):
                cleaned["color"] = ""
            return cleaned

        class Meta:
            model = CommentBadge
            fields = "__all__"

    exclude = ("config",)
    list_display = ("name", "is_owner_badge", "color", "admin_only", "enabled", "order")
    list_filter = ("is_owner_badge", "admin_only", "enabled")
    search_fields = ("name",)
    inlines = (CommentBadgeTranslationInline,)

    def save_model(self, request, obj, form, change):
        if not obj.config_id:
            obj.config = SiteConfiguration.get_config()
        super().save_model(request, obj, form, change)


@admin.register(CommentBadgeAssignment)
class CommentBadgeAssignmentAdmin(admin.ModelAdmin):
    class form(forms.ModelForm):
        color_override = forms.CharField(
            required=False,
            label=_("Colour override"),
            widget=forms.TextInput(attrs={"type": "color", "class": "vTextField"}),
        )
        inherit_badge_color = forms.BooleanField(
            required=False,
            label=_("Use badge or primary colour"),
            help_text=_("Disable this to choose a colour for this assignment only."),
        )

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.initial["inherit_badge_color"] = not bool(
                self.instance and self.instance.color_override
            )

        def clean(self):
            cleaned = super().clean()
            if cleaned.get("inherit_badge_color"):
                cleaned["color_override"] = ""
            return cleaned

        class Meta:
            model = CommentBadgeAssignment
            fields = "__all__"

    list_display = ("user", "badge", "color_override", "created_at")
    list_filter = ("badge",)
    search_fields = ("user__username", "badge__name")
    autocomplete_fields = ("user", "badge")
    readonly_fields = ("created_at",)


@admin.register(CommentEmojiPack)
class CommentEmojiPackAdmin(admin.ModelAdmin):
    exclude = ("config",)
    list_display = ("name", "enabled", "order")
    list_filter = ("enabled",)
    search_fields = ("name", "base_url")
    ordering = ("order", "id")
    inlines = (CommentEmojiInline,)

    def save_model(self, request, obj, form, change):
        if not obj.config_id:
            obj.config = SiteConfiguration.get_config()
        super().save_model(request, obj, form, change)


@admin.register(CommentEmoji)
class CommentEmojiAdmin(admin.ModelAdmin):
    list_display = ("name", "pack", "reaction_order", "order")
    list_editable = ("reaction_order", "order")
    list_filter = ("pack",)
    search_fields = ("name", "image_url", "pack__name")
    list_select_related = ("pack",)
    ordering = ("pack", "order", "id")


@admin.register(CommentGifSource)
class CommentGifSourceAdmin(admin.ModelAdmin):
    exclude = ("config",)
    list_display = ("name", "endpoint", "enabled", "order")
    list_filter = ("enabled",)
    search_fields = ("name", "endpoint")
    ordering = ("order", "id")

    def save_model(self, request, obj, form, change):
        if not obj.config_id:
            obj.config = SiteConfiguration.get_config()
        super().save_model(request, obj, form, change)


@admin.register(CommentLike)
class CommentLikeAdmin(admin.ModelAdmin):
    list_display = ("comment", "user", "created_at")
    search_fields = ("comment__content", "user__username")
    readonly_fields = ("created_at",)
    date_hierarchy = "created_at"
    list_select_related = ("comment", "user")


@admin.register(CommentNotification)
class CommentNotificationAdmin(admin.ModelAdmin):
    list_display = ("recipient", "kind", "comment", "is_read", "created_at")
    list_filter = ("kind", "is_read", "created_at")
    search_fields = ("recipient__username", "comment__content")
    readonly_fields = ("created_at",)
    date_hierarchy = "created_at"
    list_select_related = ("recipient", "actor", "comment")
    actions = ("mark_as_read", "mark_as_unread")

    @admin.action(description=_("Mark selected notifications as read"))
    def mark_as_read(self, request, queryset):
        queryset.update(is_read=True)
        self.message_user(request, _("Selected notifications were marked as read."))

    @admin.action(description=_("Mark selected notifications as unread"))
    def mark_as_unread(self, request, queryset):
        queryset.update(is_read=False)
        self.message_user(request, _("Selected notifications were marked as unread."))
