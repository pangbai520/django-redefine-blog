from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from ..models import AdminLoginRecord
from ..services.geo import get_ip_location


@admin.register(AdminLoginRecord)
class AdminLoginRecordAdmin(admin.ModelAdmin):
    list_display = (
        "username",
        "user",
        "ip_address",
        "location",
        "created_at",
    )
    list_filter = ("created_at",)
    search_fields = ("username", "user__username", "ip_address", "user_agent")
    readonly_fields = (
        "user",
        "username",
        "ip_address",
        "location",
        "user_agent",
        "created_at",
    )
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_select_related = ("user",)
    list_per_page = 100

    @admin.display(description=_("Location"))
    def location(self, obj):
        return get_ip_location(obj.ip_address) or _("Unknown")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
