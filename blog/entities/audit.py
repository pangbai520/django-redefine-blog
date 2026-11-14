from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class AdminLoginRecord(models.Model):
    """A successful sign-in to the real Django administration site."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="admin_login_records",
        verbose_name=_("Account"),
    )
    username = models.CharField(_("Username"), max_length=150, db_index=True)
    ip_address = models.GenericIPAddressField(
        _("IP address"), null=True, blank=True, db_index=True
    )
    user_agent = models.CharField(_("User agent"), max_length=255, blank=True)
    created_at = models.DateTimeField(_("Created at"), auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("user", "created_at")),
            models.Index(fields=("ip_address", "created_at")),
        ]

    def __str__(self):
        return f"{self.username}: {self.ip_address or 'unknown'}"
