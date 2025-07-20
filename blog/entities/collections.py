from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from blog.validators import validate_theme_image


class AudioTrack(models.Model):
    name = models.CharField(max_length=150)
    artist = models.CharField(max_length=150, blank=True)
    url = models.CharField(
        max_length=500,
        blank=True,
        help_text="External URL or a path under the site media/static files.",
    )
    audio_file = models.FileField(upload_to="audio/", blank=True)
    cover = models.CharField(max_length=500, blank=True)
    cover_image = models.FileField(
        upload_to="audio_covers/",
        blank=True,
        null=True,
        validators=[validate_theme_image],
    )
    lrc = models.TextField(blank=True)
    theme = models.CharField(max_length=20, blank=True)
    enabled = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("order", "id")
        verbose_name = "Audio track"
        verbose_name_plural = "Audio tracks"

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if not self.url and not self.audio_file:
            raise ValidationError("Provide an audio URL or upload an audio file.")


class BookmarkCategory(models.Model):
    config = models.ForeignKey(
        "blog.SiteConfiguration",
        on_delete=models.CASCADE,
        related_name="bookmark_categories",
    )
    name = models.CharField(max_length=100)
    icon = models.CharField(max_length=100, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("order", "id")
        verbose_name = "Bookmark category"
        verbose_name_plural = "Bookmark categories"

    def __str__(self):
        return self.name


class Bookmark(models.Model):
    category = models.ForeignKey(
        BookmarkCategory,
        on_delete=models.CASCADE,
        related_name="items",
    )
    name = models.CharField(max_length=100)
    link = models.URLField()
    image = models.URLField(blank=True)
    description = models.CharField(max_length=255, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("order", "id")
        verbose_name = "Bookmark"
        verbose_name_plural = "Bookmarks"

    def __str__(self):
        return self.name


class Essay(models.Model):
    config = models.ForeignKey(
        "blog.SiteConfiguration",
        on_delete=models.CASCADE,
        related_name="essays",
    )
    content = models.TextField()
    published = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Essay"
        verbose_name_plural = "Essays"

    def __str__(self):
        return self.content[:60]


class MasonryImage(models.Model):
    config = models.ForeignKey(
        "blog.SiteConfiguration",
        on_delete=models.CASCADE,
        related_name="masonry_images",
    )
    image = models.URLField()
    title = models.CharField(max_length=150, blank=True)
    description = models.CharField(max_length=255, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("order", "id")
        verbose_name = "Masonry image"
        verbose_name_plural = "Masonry images"

    def __str__(self):
        return self.title or self.image


class FriendCategory(models.Model):
    name = models.CharField(max_length=100)
    has_thumbnail = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("order", "id")
        verbose_name = "Friend category"
        verbose_name_plural = "Friend categories"

    def __str__(self):
        return self.name


class FriendLink(models.Model):
    category = models.ForeignKey(
        FriendCategory,
        on_delete=models.CASCADE,
        related_name="links",
    )
    name = models.CharField(max_length=100)
    link = models.URLField()
    avatar = models.URLField(blank=True)
    thumbnail = models.URLField(blank=True)
    description = models.CharField(max_length=255, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("order", "id")
        verbose_name = "Friend link"
        verbose_name_plural = "Friend links"

    def __str__(self):
        return self.name
