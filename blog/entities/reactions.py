import hashlib

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
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Article reaction vote")
        verbose_name_plural = _("Article reaction votes")
        constraints = [
            models.UniqueConstraint(
                fields=("article", "visitor"),
                name="unique_article_reaction_visitor",
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
