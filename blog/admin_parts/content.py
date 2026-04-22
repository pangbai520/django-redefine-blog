from django import forms
from django.contrib import admin
from django.db import models
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _, ngettext

from blog.models import (
    ArticleModel,
    ArticleReactionVote,
    AudioTrack,
    Bookmark,
    BookmarkCategory,
    Category,
    Essay,
    FriendCategory,
    FriendLink,
    MasonryImage,
    SiteConfiguration,
    Tag,
    TrafficModel,
)
from blog.services.geo import get_ip_location


@admin.register(ArticleModel)
class ArticleAdmin(admin.ModelAdmin):
    formfield_overrides = {
        models.ManyToManyField: {"widget": forms.CheckboxSelectMultiple},
    }
    list_display = (
        "title",
        "publication_state",
        "writer",
        "created_at",
        "updated_at",
        "sticky",
        "word_counter",
        "reading_time",
        "view_count",
        "show_comment",
        "show_reaction",
    )
    list_filter = ("is_published", "created_at", "category", "tags")
    search_fields = ("title", "slug", "writer", "excerpt", "content")
    filter_horizontal = ("category", "tags")
    readonly_fields = (
        "slug",
        "word_counter",
        "reading_time",
        "view_count",
        "updated_at",
    )
    date_hierarchy = "created_at"
    ordering = ("-sticky", "-created_at")
    list_per_page = 40
    save_on_top = True
    actions = (
        "publish_articles",
        "unpublish_articles",
        "enable_comments",
        "disable_comments",
        "enable_reactions",
        "disable_reactions",
    )

    @admin.display(description=_("Publication status"), ordering="is_published")
    def publication_state(self, obj):
        label = _("Published") if obj.is_published else _("Draft")
        css_class = (
            "admin-status admin-status-active" if obj.is_published else "admin-status"
        )
        return format_html('<span class="{}">{}</span>', css_class, label)

    @admin.action(description=_("Publish selected articles"))
    def publish_articles(self, request, queryset):
        updated = queryset.update(is_published=True)
        from ..cache_utils import invalidate_content_caches
        from ..services.search import index_article

        for article in queryset.iterator():
            index_article(article)
        invalidate_content_caches()
        self.message_user(
            request,
            ngettext(
                "Published %(count)d article.",
                "Published %(count)d articles.",
                updated,
            )
            % {"count": updated},
        )

    @admin.action(description=_("Move selected articles to drafts"))
    def unpublish_articles(self, request, queryset):
        updated = queryset.update(is_published=False)
        from ..cache_utils import invalidate_content_caches
        from ..services.search import index_article

        for article in queryset.iterator():
            index_article(article)
        invalidate_content_caches()
        self.message_user(
            request,
            ngettext(
                "Moved %(count)d article to drafts.",
                "Moved %(count)d articles to drafts.",
                updated,
            )
            % {"count": updated},
        )

    @admin.action(description=_("Enable comments on selected articles"))
    def enable_comments(self, request, queryset):
        updated = queryset.update(show_comment=True)
        self.message_user(
            request,
            ngettext(
                "Enabled comments on %(count)d article.",
                "Enabled comments on %(count)d articles.",
                updated,
            )
            % {"count": updated},
        )

    @admin.action(description=_("Disable comments on selected articles"))
    def disable_comments(self, request, queryset):
        updated = queryset.update(show_comment=False)
        self.message_user(
            request,
            ngettext(
                "Disabled comments on %(count)d article.",
                "Disabled comments on %(count)d articles.",
                updated,
            )
            % {"count": updated},
        )

    @admin.action(description=_("Enable reactions on selected articles"))
    def enable_reactions(self, request, queryset):
        queryset.update(show_reaction=True)
        self.message_user(request, _("Enabled"))

    @admin.action(description=_("Disable reactions on selected articles"))
    def disable_reactions(self, request, queryset):
        queryset.update(show_reaction=False)
        self.message_user(request, _("Disabled"))


@admin.register(ArticleReactionVote)
class ArticleReactionVoteAdmin(admin.ModelAdmin):
    list_display = (
        "article",
        "reaction_preview",
        "viewer",
        "source",
        "updated_at",
    )
    list_filter = ("reaction", "updated_at")
    search_fields = (
        "article__title",
        "user__username",
        "ip_address",
        "visitor",
        "user_agent",
    )
    readonly_fields = (
        "article",
        "reaction",
        "user",
        "ip_address",
        "user_agent",
        "visitor",
        "updated_at",
    )
    ordering = ("-updated_at",)
    date_hierarchy = "updated_at"
    list_select_related = ("article", "user")

    @admin.display(description=_("Reaction"), ordering="reaction")
    def reaction_preview(self, obj):
        options = SiteConfiguration.get_config().article_reaction_options
        if obj.reaction >= len(options):
            return f"#{obj.reaction + 1}"
        option = options[obj.reaction]
        return format_html(
            '<span class="admin-reaction-preview"><img src="{}" alt="" referrerpolicy="no-referrer" loading="lazy"> {}</span>',
            option["image_url"],
            option["name"] or f"#{obj.reaction + 1}",
        )

    @admin.display(description=_("Visitor"), ordering="user__username")
    def viewer(self, obj):
        if obj.user_id:
            return obj.user.get_username()
        return _("Anonymous browser %(identifier)s") % {
            "identifier": obj.visitor[:10]
        }

    @admin.display(description=_("IP address / location"), ordering="ip_address")
    def source(self, obj):
        if not obj.ip_address:
            return "-"
        location = get_ip_location(obj.ip_address)
        if location:
            return f"{location} ({obj.ip_address})"
        return obj.ip_address

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AudioTrack)
class AudioTrackAdmin(admin.ModelAdmin):
    list_display = ("name", "artist", "enabled", "order")
    list_filter = ("enabled",)
    search_fields = ("name", "artist")
    ordering = ("order", "id")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "parent")
    search_fields = ("name", "slug")
    autocomplete_fields = ("parent",)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name", "slug")
    ordering = ("name",)


@admin.register(BookmarkCategory)
class BookmarkCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "config", "order")
    list_filter = ("config",)
    ordering = ("config", "order")
    search_fields = ("name", "icon", "config__config_name")
    list_select_related = ("config",)


@admin.register(Bookmark)
class BookmarkAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "order")
    list_filter = ("category__config", "category")
    ordering = ("category", "order")
    search_fields = ("name", "link", "description", "category__name")
    list_select_related = ("category",)


@admin.register(Essay)
class EssayAdmin(admin.ModelAdmin):
    list_display = ("created_at", "config", "published")
    list_filter = ("config", "published")
    ordering = ("-created_at",)
    search_fields = ("content", "config__config_name")
    date_hierarchy = "created_at"
    list_select_related = ("config",)


@admin.register(MasonryImage)
class MasonryImageAdmin(admin.ModelAdmin):
    list_display = ("title", "config", "order")
    list_filter = ("config",)
    ordering = ("config", "order")
    search_fields = ("title", "description", "image", "config__config_name")
    list_select_related = ("config",)


class FriendLinkInline(admin.TabularInline):
    model = FriendLink
    extra = 1
    fields = ("name", "link", "avatar", "thumbnail", "description", "order")


@admin.register(FriendCategory)
class FriendCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "has_thumbnail", "order")
    ordering = ("order", "id")
    inlines = (FriendLinkInline,)
    search_fields = ("name",)


@admin.register(FriendLink)
class FriendLinkAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "order")
    list_filter = ("category",)
    search_fields = ("name", "description")
    ordering = ("category", "order", "id")
    list_select_related = ("category",)


@admin.register(TrafficModel)
class TrafficAdmin(admin.ModelAdmin):
    list_display = ("path", "ip", "user_agent", "created_at")
    list_filter = ("created_at",)
    search_fields = ("path", "ip", "user_agent")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    readonly_fields = ("path", "ip", "user_agent", "created_at")
    list_per_page = 100

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
