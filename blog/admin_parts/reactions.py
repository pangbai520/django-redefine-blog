import hashlib

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from blog.models import ArticleRatingEmoji, CommentEmojiPack, SiteConfiguration
from blog.services.emoji import emoji_items


def emoji_key(image_url):
    return hashlib.sha256(image_url.encode("utf-8")).hexdigest()


class ArticleRatingEmojiForm(forms.ModelForm):
    emoji = forms.ChoiceField(
        label=_("Choose an emoji"),
        widget=forms.RadioSelect(attrs={"class": "article-rating-picker"}),
    )

    class Meta:
        model = ArticleRatingEmoji
        fields = ("position", "emoji")
        widgets = {
            "position": forms.Select(choices=[(value, value) for value in range(1, 10)])
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        site = SiteConfiguration.get_config()
        self.emoji_map = {}
        groups = []
        for pack in CommentEmojiPack.objects.filter(
            config=site,
            enabled=True,
        ).prefetch_related("items"):
            choices = []
            for item in emoji_items(pack):
                name = str(item.get("name", "")).strip()
                image_url = str(item.get("url", "")).strip()
                if not name or not image_url:
                    continue
                key = emoji_key(image_url)
                self.emoji_map[key] = (name, image_url)
                choices.append(
                    (
                        key,
                        format_html(
                            '<img src="{}" alt="" loading="lazy" referrerpolicy="no-referrer">'
                            '<span>{}</span>',
                            image_url,
                            name,
                        ),
                    )
                )
            if choices:
                groups.append((pack.name, choices))

        if self.instance.pk:
            current_key = emoji_key(self.instance.image_url)
            if current_key not in self.emoji_map:
                self.emoji_map[current_key] = (
                    self.instance.name,
                    self.instance.image_url,
                )
                groups.append(
                    (
                        _("Current selection"),
                        [
                            (
                                current_key,
                                format_html(
                                    '<img src="{}" alt="" loading="lazy" '
                                    'referrerpolicy="no-referrer"><span>{}</span>',
                                    self.instance.image_url,
                                    self.instance.name,
                                ),
                            )
                        ],
                    )
                )
            self.initial["emoji"] = current_key

        self.fields["emoji"].choices = groups
        if not groups:
            self.fields["emoji"].help_text = _(
                "No enabled emoji pack contains selectable emojis. Add or enable a comment emoji pack first."
            )

    def clean_emoji(self):
        key = self.cleaned_data["emoji"]
        try:
            self.selected_emoji = self.emoji_map[key]
        except KeyError as exc:
            raise ValidationError(_("Select a valid emoji.")) from exc
        return key

    def clean(self):
        cleaned = super().clean()
        site = SiteConfiguration.get_config()
        if not self.instance.pk and site.article_rating_emojis.count() >= 9:
            raise ValidationError(_("Article ratings can use at most 9 emojis."))
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.config = SiteConfiguration.get_config()
        instance.name, instance.image_url = self.selected_emoji
        if commit:
            instance.save()
        return instance


@admin.register(ArticleRatingEmoji)
class ArticleRatingEmojiAdmin(admin.ModelAdmin):
    form = ArticleRatingEmojiForm
    list_display = ("position", "preview", "name")
    ordering = ("position", "id")

    def get_queryset(self, request):
        return super().get_queryset(request).filter(config=SiteConfiguration.get_config())

    @admin.display(description=_("Preview"))
    def preview(self, obj):
        return format_html(
            '<img src="{}" alt="" width="36" height="36" '
            'style="object-fit:contain" referrerpolicy="no-referrer">',
            obj.image_url,
        )

    class Media:
        css = {"all": ("css/admin/article-rating.css",)}
