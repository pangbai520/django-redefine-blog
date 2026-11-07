from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class EditorImage(models.Model):
    image = models.ImageField(_("image"), upload_to="editor/")
    digest = models.CharField(_("file hash"), max_length=64, unique=True)
    original_name = models.CharField(_("original filename"), max_length=255, blank=True)
    uploader = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="editor_images",
        verbose_name=_("uploader"),
    )
    size = models.PositiveBigIntegerField(_("file size"), default=0)
    width = models.PositiveIntegerField(_("width"), default=0)
    height = models.PositiveIntegerField(_("height"), default=0)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = _("article image")
        verbose_name_plural = _("article images")

    def __str__(self):
        return self.original_name or self.image.name


class EditorImageRef(models.Model):
    ARTICLE = "article"
    PAGE = "page"
    TRANSLATION = "translation"
    TARGET_CHOICES = (
        (ARTICLE, _("article")),
        (PAGE, _("standalone page")),
        (TRANSLATION, _("page translation")),
    )

    image = models.ForeignKey(
        EditorImage,
        on_delete=models.CASCADE,
        related_name="refs",
        verbose_name=_("image"),
    )
    target_type = models.CharField(
        _("reference type"), max_length=20, choices=TARGET_CHOICES
    )
    target_id = models.PositiveBigIntegerField(_("referenced object"))

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("image", "target_type", "target_id"),
                name="unique_editor_image_reference",
            )
        ]
        indexes = [models.Index(fields=("target_type", "target_id"))]
        verbose_name = _("article image reference")
        verbose_name_plural = _("article image references")

    def __str__(self):
        return f"{self.image_id}:{self.target_type}:{self.target_id}"
