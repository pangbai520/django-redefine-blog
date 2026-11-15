import hashlib

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


class ArticleReactionVote(models.Model):
    """One anonymous browser vote for an article reaction."""

    article = models.ForeignKey(
        "blog.ArticleModel",
        on_delete=models.CASCADE,
        related_name="reaction_votes",
    )
    visitor = models.CharField(max_length=64)
    reaction = models.PositiveSmallIntegerField()
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="article_reaction_votes",
    )
    ip_address = models.GenericIPAddressField(blank=True, null=True, db_index=True)
    user_agent = models.CharField(max_length=255, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Article rating")
        verbose_name_plural = _("Article ratings")
        constraints = [
            models.UniqueConstraint(
                fields=("article", "visitor"),
                name="unique_article_reaction_visitor",
            ),
            models.UniqueConstraint(
                fields=("article", "user"),
                condition=models.Q(user__isnull=False),
                name="unique_article_reaction_user",
            ),
            models.CheckConstraint(
                condition=models.Q(reaction__gte=0, reaction__lte=8),
                name="article_reaction_index_range",
            ),
        ]
        indexes = [models.Index(fields=("article", "reaction"))]

    @staticmethod
    def visitor_hash(token):
        return hashlib.sha256(token.encode("utf-8")).hexdigest()


class ArticleRatingEmoji(models.Model):
    """One explicitly selected icon in the article rating bar."""

    config = models.ForeignKey(
        "blog.SiteConfiguration",
        on_delete=models.CASCADE,
        related_name="article_rating_emojis",
    )
    name = models.CharField(_("Name"), max_length=80)
    image_url = models.URLField(_("Image URL"), max_length=500)
    position = models.PositiveSmallIntegerField(
        _("Rating position"),
        validators=[MinValueValidator(1), MaxValueValidator(9)],
    )

    class Meta:
        verbose_name = _("Article rating emoji")
        verbose_name_plural = _("Article rating emojis")
        ordering = ("position", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("config", "position"),
                name="unique_article_rating_position",
            ),
            models.UniqueConstraint(
                fields=("config", "image_url"),
                name="unique_article_rating_emoji",
            ),
            models.CheckConstraint(
                condition=models.Q(position__gte=1, position__lte=9),
                name="article_rating_position_range",
            ),
        ]

    def __str__(self):
        return f"{self.position}. {self.name}"
