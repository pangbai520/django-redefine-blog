from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _, ngettext

from blog.models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "display_name",
        "website",
        "review_pending",
        "pending_email",
        "pending_email_requested_at",
    )
    list_filter = ("profile_review_pending",)
    search_fields = (
        "user__username",
        "user__email",
        "display_name",
        "website",
        "pending_display_name",
        "pending_website",
        "pending_email",
    )
    raw_id_fields = ("user",)
    readonly_fields = (
        "avatar_preview",
        "pending_avatar_preview",
        "profile_review_requested_at",
        "pending_email_requested_at",
    )
    list_select_related = ("user",)
    actions = ("approve_profile_changes", "reject_profile_changes")
    fieldsets = (
        (
            _("Public profile"),
            {"fields": ("user", "display_name", "website", "avatar", "avatar_preview")},
        ),
        (
            _("Pending profile review"),
            {
                "fields": (
                    "profile_review_pending",
                    "profile_review_requested_at",
                    "pending_display_name",
                    "pending_website",
                    "pending_avatar",
                    "pending_avatar_preview",
                    "pending_avatar_change",
                )
            },
        ),
        (
            _("Pending email change"),
            {"fields": ("pending_email", "pending_email_requested_at")},
        ),
    )

    def get_queryset(self, request):
        # A public profile is created only after email verification. Hide any
        # legacy profile rows belonging to still-inactive accounts as well.
        return super().get_queryset(request).filter(user__is_active=True)

    @admin.display(
        description=_("Review pending"), boolean=True, ordering="profile_review_pending"
    )
    def review_pending(self, obj):
        return obj.profile_review_pending

    @admin.display(description=_("Current avatar"))
    def avatar_preview(self, obj):
        if not obj.avatar:
            return "—"
        return format_html(
            '<img src="{}" alt="" style="width:72px;height:72px;object-fit:contain;'
            'border-radius:14px;background:var(--body-bg);">',
            obj.avatar.url,
        )

    @admin.display(description=_("Pending avatar"))
    def pending_avatar_preview(self, obj):
        if not obj.profile_review_pending or not obj.pending_avatar_change:
            return _("No avatar change")
        if not obj.pending_avatar:
            return _("Remove current avatar")
        return format_html(
            '<img src="{}" alt="" style="width:72px;height:72px;object-fit:contain;'
            'border-radius:14px;background:var(--body-bg);">',
            obj.pending_avatar.url,
        )

    @admin.action(description=_("Approve selected profile changes"))
    def approve_profile_changes(self, request, queryset):
        approved = 0
        for profile in queryset.filter(profile_review_pending=True).iterator():
            approved += int(profile.approve_pending())
        self.message_user(
            request,
            ngettext(
                "Approved %(count)d profile change.",
                "Approved %(count)d profile changes.",
                approved,
            )
            % {"count": approved},
            messages.SUCCESS,
        )

    @admin.action(description=_("Reject selected profile changes"))
    def reject_profile_changes(self, request, queryset):
        rejected = 0
        for profile in queryset.filter(profile_review_pending=True).iterator():
            profile.clear_pending()
            rejected += 1
        self.message_user(
            request,
            ngettext(
                "Rejected %(count)d profile change.",
                "Rejected %(count)d profile changes.",
                rejected,
            )
            % {"count": rejected},
            messages.SUCCESS,
        )
