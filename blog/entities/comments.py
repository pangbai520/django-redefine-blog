from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django_cleanup.cleanup import cleanup_ignore


class Comment(models.Model):
    """A comment attached to an article or standalone page."""

    article = models.ForeignKey(
        "blog.ArticleModel",
        on_delete=models.CASCADE,
        related_name="comments",
        null=True,
        blank=True,
    )
    page = models.ForeignKey(
        "blog.StandalonePage",
        on_delete=models.CASCADE,
        related_name="comments",
        null=True,
        blank=True,
    )
    author = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="blog_comments",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="replies",
    )
    nickname = models.CharField(max_length=80, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)
    author_deleted = models.BooleanField(default=False)
    content = models.TextField(max_length=5000)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    browser = models.CharField(max_length=120, blank=True)
    operating_system = models.CharField(max_length=120, blank=True)
    is_sticky = models.BooleanField(default=False, db_index=True)
    is_approved = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(article__isnull=False, page__isnull=True)
                    | Q(article__isnull=True, page__isnull=False)
                ),
                name="comment_has_exactly_one_target",
            ),
            models.UniqueConstraint(
                fields=("article",),
                condition=Q(is_sticky=True, article__isnull=False),
                name="unique_sticky_comment_per_article",
            ),
            models.UniqueConstraint(
                fields=("page",),
                condition=Q(is_sticky=True, page__isnull=False),
                name="unique_sticky_comment_per_page",
            ),
        ]

    @property
    def display_name(self):
        if self.author_deleted:
            return _("Deleted user")
        if self.author_id:
            profile = getattr(self.author, "profile", None)
            if profile and profile.display_name.strip():
                return profile.display_name.strip()
            return self.author.get_full_name() or self.author.username
        return self.nickname or "Anonymous"

    @property
    def avatar_url(self):
        if self.author_id and hasattr(self.author, "profile"):
            avatar = getattr(self.author.profile, "avatar", None)
            if avatar:
                return avatar.url
        return ""

    @property
    def like_count(self):
        return self.likes.count()

    def clean(self):
        if bool(self.article_id) == bool(self.page_id):
            raise ValidationError(
                _("A comment must belong to exactly one article or page.")
            )
        if self.parent_id:
            if self.parent_id == self.pk:
                raise ValidationError("A comment cannot reply to itself.")
            if self.parent.article_id != self.article_id:
                raise ValidationError(_("A reply must belong to the same page."))
            if self.parent.page_id != self.page_id:
                raise ValidationError(_("A reply must belong to the same page."))
            ancestor = self.parent
            visited = set()
            while ancestor is not None:
                if ancestor.pk in visited or (self.pk and ancestor.pk == self.pk):
                    raise ValidationError("Comment replies cannot form a cycle.")
                visited.add(ancestor.pk)
                ancestor = ancestor.parent
        if self.author_id:
            self.nickname = ""
            self.email = ""
        elif not self.nickname and not self.author_deleted:
            raise ValidationError({"nickname": "Guest comments require a nickname."})

    def save(self, *args, **kwargs):
        if not self.is_sticky:
            return super().save(*args, **kwargs)

        # MySQL does not create conditional unique constraints. Lock the
        # article row so concurrent saves still agree on a single pinned
        # comment, while PostgreSQL and SQLite retain the database constraint
        # as an additional safeguard.
        with transaction.atomic():
            if self.article_id:
                type(self.article).objects.select_for_update().filter(
                    pk=self.article_id
                ).exists()
                target = {"article_id": self.article_id}
            else:
                type(self.page).objects.select_for_update().filter(
                    pk=self.page_id
                ).exists()
                target = {"page_id": self.page_id}
            type(self).objects.filter(is_sticky=True, **target).exclude(
                pk=self.pk
            ).update(is_sticky=False)
            return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.display_name}: {self.content[:40]}"


@cleanup_ignore
class CommentImage(models.Model):
    """An uploaded comment image, retained only while a comment references it."""

    uploader = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comment_images",
    )
    comment = models.ForeignKey(
        Comment,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="images",
    )
    image = models.ImageField(upload_to="comment-images/")
    content_hash = models.CharField(max_length=64, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return self.image.name


class CommentLike(models.Model):
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name="likes")
    user = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, related_name="comment_likes"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("comment", "user"), name="unique_comment_like"
            ),
        ]


class CommentNotification(models.Model):
    REPLY = "reply"
    LIKE = "like"
    KIND_CHOICES = ((REPLY, "Reply"), (LIKE, "Like"))

    recipient = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, related_name="comment_notifications"
    )
    actor = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comment_actions",
    )
    comment = models.ForeignKey(
        Comment, on_delete=models.CASCADE, related_name="notifications"
    )
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)


class CommentBadge(models.Model):
    """A configurable label that can be granted to registered commenters."""

    config = models.ForeignKey(
        "blog.SiteConfiguration",
        on_delete=models.CASCADE,
        related_name="comment_badges",
    )
    name = models.CharField(max_length=40)
    is_owner_badge = models.BooleanField(
        _("owner badge"),
        default=False,
        help_text=_("Automatically grant this badge to active superusers."),
    )
    # an empty value inherits the active theme colour
    color = models.CharField(max_length=32, default="", blank=True)
    admin_only = models.BooleanField(default=True)
    enabled = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("order", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("config", "name"), name="unique_comment_badge_name"
            ),
            models.UniqueConstraint(
                fields=("config",),
                condition=Q(is_owner_badge=True),
                name="unique_owner_badge_per_config",
            ),
        ]

    def localized_name(self, language_code=None):
        from django.utils.translation import get_language

        language_code = (
            (language_code or get_language() or "").replace("_", "-").lower()
        )
        translations = list(self.translations.all())
        for candidate in (language_code, language_code.split("-", 1)[0]):
            for translation in translations:
                if translation.language_code.replace("_", "-").lower() == candidate:
                    return translation.name
        return self.name

    def __str__(self):
        return self.name


class CommentBadgeTranslation(models.Model):
    badge = models.ForeignKey(
        CommentBadge, on_delete=models.CASCADE, related_name="translations"
    )
    language_code = models.CharField(
        _("language code"), max_length=20, choices=settings.LANGUAGES
    )
    name = models.CharField(_("translated badge name"), max_length=40)

    class Meta:
        ordering = ("language_code", "id")
        verbose_name = _("comment badge translation")
        verbose_name_plural = _("comment badge translations")
        constraints = [
            models.UniqueConstraint(
                fields=("badge", "language_code"),
                name="unique_comment_badge_translation_language",
            )
        ]

    def __str__(self):
        return f"{self.badge.name} ({self.language_code})"


class CommentBadgeAssignment(models.Model):
    user = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, related_name="comment_badges"
    )
    badge = models.ForeignKey(
        CommentBadge, on_delete=models.CASCADE, related_name="assignments"
    )
    # an empty value inherits the badge colour
    color_override = models.CharField(max_length=32, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("badge__order", "badge_id")
        constraints = [
            models.UniqueConstraint(
                fields=("user", "badge"),
                name="unique_comment_badge_assignment",
            ),
        ]


class CommentEmojiPack(models.Model):
    config = models.ForeignKey(
        "blog.SiteConfiguration",
        on_delete=models.CASCADE,
        related_name="comment_emoji_packs",
    )
    name = models.CharField(max_length=80)
    base_url = models.URLField(blank=True)
    enabled = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("order", "id")

    def __str__(self):
        return self.name


class CommentEmoji(models.Model):
    pack = models.ForeignKey(
        CommentEmojiPack, on_delete=models.CASCADE, related_name="items"
    )
    name = models.CharField(max_length=80)
    image_url = models.URLField()
    reaction_order = models.PositiveSmallIntegerField(
        _("Article reaction slot"),
        blank=True,
        null=True,
        validators=[MinValueValidator(1), MaxValueValidator(9)],
        help_text=_("Set a unique slot from 1 to 9, or leave empty to hide it."),
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("order", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("pack", "reaction_order"),
                condition=Q(reaction_order__isnull=False),
                name="unique_reaction_slot_per_pack",
            ),
            models.CheckConstraint(
                condition=(
                    Q(reaction_order__isnull=True)
                    | Q(reaction_order__gte=1, reaction_order__lte=9)
                ),
                name="comment_emoji_reaction_slot_range",
            ),
        ]

    def __str__(self):
        return f"{self.pack.name}: {self.name}"


class CommentGifSource(models.Model):
    config = models.ForeignKey(
        "blog.SiteConfiguration",
        on_delete=models.CASCADE,
        related_name="comment_gif_sources",
    )
    name = models.CharField(max_length=80)
    endpoint = models.URLField()
    enabled = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("order", "id")

    def __str__(self):
        return self.name


class TrafficModel(models.Model):
    path = models.CharField(max_length=255, db_index=True)
    ip = models.GenericIPAddressField(db_index=True)
    user_agent = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["ip", "path", "created_at"]),
        ]
        ordering = ["-created_at"]
        verbose_name = "访问记录"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.ip} -> {self.path}"
