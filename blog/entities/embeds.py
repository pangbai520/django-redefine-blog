import re

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _


HOST_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)


class EmbedProvider(models.Model):
    name = models.CharField(_("name"), max_length=100)
    host = models.CharField(
        _("allowed host"),
        max_length=253,
        help_text=_("Enter an exact host without a scheme, path, port, or wildcard."),
    )
    path_prefix = models.CharField(
        _("allowed path prefix"),
        max_length=255,
        default="/",
        help_text=_(
            "Only HTTPS iframe URLs on this path are accepted. "
            "Use /embed/ for a directory or /player.html for one endpoint."
        ),
    )
    enabled = models.BooleanField(_("enabled"), default=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        ordering = ("name", "host", "path_prefix")
        constraints = [
            models.UniqueConstraint(
                fields=("host", "path_prefix"),
                name="unique_embed_provider_rule",
            )
        ]
        verbose_name = _("trusted embed provider")
        verbose_name_plural = _("trusted embed providers")

    def __str__(self):
        return f"{self.name} ({self.host}{self.path_prefix})"

    def clean(self):
        super().clean()
        host = (self.host or "").strip().lower().rstrip(".")
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError:
            raise ValidationError({"host": _("Enter a valid public domain name.")})
        if not HOST_RE.fullmatch(host):
            raise ValidationError({"host": _("Enter a valid public domain name.")})

        path_prefix = (self.path_prefix or "/").strip()
        if (
            not path_prefix.startswith("/")
            or "?" in path_prefix
            or "#" in path_prefix
            or "\\" in path_prefix
        ):
            raise ValidationError(
                {"path_prefix": _("Enter a path beginning with / without a query or fragment.")}
            )

        self.host = host
        self.path_prefix = path_prefix

