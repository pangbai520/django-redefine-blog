import uuid
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from blog.validators import validate_profile_avatar


def avatar_path(instance, filename):
    suffix = Path(filename).suffix.lower()
    return f"user-avatars/{instance.user_id}/{uuid.uuid4().hex}{suffix}"


class PendingRegistration(models.Model):
    """Tracks accounts that still need to prove ownership of their email."""

    user = models.OneToOneField(
        "auth.User",
        on_delete=models.CASCADE,
        related_name="pending_registration",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("created_at",)

    def __str__(self):
        return self.user.get_username()


class UserProfile(models.Model):
    """Public-facing identity for a registered comment account."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    display_name = models.CharField(_("display name"), max_length=80, blank=True)
    website = models.URLField(_("personal website"), blank=True)
    avatar = models.ImageField(
        _("avatar"),
        upload_to=avatar_path,
        blank=True,
        validators=[validate_profile_avatar],
    )
    pending_display_name = models.CharField(
        _("pending display name"), max_length=80, blank=True
    )
    pending_website = models.URLField(_("pending personal website"), blank=True)
    pending_avatar = models.ImageField(
        _("pending avatar"),
        upload_to=avatar_path,
        blank=True,
        validators=[validate_profile_avatar],
    )
    pending_avatar_change = models.BooleanField(default=False)
    profile_review_pending = models.BooleanField(default=False, db_index=True)
    profile_review_requested_at = models.DateTimeField(null=True, blank=True)
    pending_email = models.EmailField(_("pending email"), blank=True)
    pending_email_requested_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("user__username",)

    @property
    def resolved_display_name(self):
        return (
            self.display_name.strip()
            or self.user.get_full_name()
            or self.user.get_username()
        )

    @property
    def pending_name(self):
        return (
            self.pending_display_name.strip()
            or self.user.get_full_name()
            or self.user.get_username()
        )

    def stage_profile_changes(
        self, *, display_name, website="", avatar=None, remove_avatar=False
    ):
        """Store a public identity draft without changing the live profile."""
        replaced_storage = self.pending_avatar.storage if self.pending_avatar else None
        replaced_name = self.pending_avatar.name if self.pending_avatar else ""
        self.pending_display_name = display_name.strip()
        self.pending_website = website.strip()
        if avatar is not None:
            self.pending_avatar = avatar
            self.pending_avatar_change = True
        elif remove_avatar:
            self.pending_avatar = None
            self.pending_avatar_change = True
        elif not self.profile_review_pending:
            self.pending_avatar_change = False
        self.profile_review_pending = True
        self.profile_review_requested_at = timezone.now()
        self.save(
            update_fields=(
                "pending_display_name",
                "pending_website",
                "pending_avatar",
                "pending_avatar_change",
                "profile_review_pending",
                "profile_review_requested_at",
            )
        )
        if replaced_name and replaced_name != self.pending_avatar.name:
            transaction.on_commit(
                lambda storage=replaced_storage, name=replaced_name: storage.delete(
                    name
                )
            )

    def clear_pending(self):
        pending_storage = self.pending_avatar.storage if self.pending_avatar else None
        pending_name = self.pending_avatar.name if self.pending_avatar else ""
        self.pending_display_name = ""
        self.pending_website = ""
        self.pending_avatar = None
        self.pending_avatar_change = False
        self.profile_review_pending = False
        self.profile_review_requested_at = None
        self.save(
            update_fields=(
                "pending_display_name",
                "pending_website",
                "pending_avatar",
                "pending_avatar_change",
                "profile_review_pending",
                "profile_review_requested_at",
            )
        )
        if pending_name:
            transaction.on_commit(
                lambda storage=pending_storage, name=pending_name: storage.delete(name)
            )

    def approve_pending(self):
        """Publish the staged identity and leave unrelated account data alone."""
        if not self.profile_review_pending:
            return False

        pending_storage = self.pending_avatar.storage if self.pending_avatar else None
        pending_name = self.pending_avatar.name if self.pending_avatar else ""
        self.display_name = self.pending_display_name
        self.website = self.pending_website
        if self.pending_avatar_change:
            if self.pending_avatar:
                self.pending_avatar.open("rb")
                try:
                    copied_avatar = ContentFile(
                        self.pending_avatar.read(),
                        name=Path(self.pending_avatar.name).name,
                    )
                finally:
                    self.pending_avatar.close()
                self.avatar.save(copied_avatar.name, copied_avatar, save=False)
            else:
                self.avatar = None

        self.pending_display_name = ""
        self.pending_website = ""
        self.pending_avatar = None
        self.pending_avatar_change = False
        self.profile_review_pending = False
        self.profile_review_requested_at = None
        self.save(
            update_fields=(
                "display_name",
                "website",
                "avatar",
                "pending_display_name",
                "pending_website",
                "pending_avatar",
                "pending_avatar_change",
                "profile_review_pending",
                "profile_review_requested_at",
            )
        )
        if pending_name:
            transaction.on_commit(
                lambda storage=pending_storage, name=pending_name: storage.delete(name)
            )
        return True

    def __str__(self):
        return self.resolved_display_name
