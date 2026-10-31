import io
from pathlib import Path

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.translation import gettext_lazy as _
from PIL import Image, ImageOps, UnidentifiedImageError

from .models import UserProfile


User = get_user_model()


class CommentRegistrationForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        label=_("Username"),
        help_text=_("Your username cannot be changed after registration."),
    )
    email = forms.EmailField(label=_("Email"))
    password = forms.CharField(widget=forms.PasswordInput, min_length=8, label=_("Password"))
    password_confirm = forms.CharField(widget=forms.PasswordInput, label=_("Confirm password"))

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError(_("This username is already in use."))
        return username

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(_("This email address is already registered."))
        return email

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password")
        if password:
            try:
                candidate = User(
                    username=cleaned.get("username", ""),
                    email=cleaned.get("email", ""),
                )
                validate_password(password, user=candidate)
            except forms.ValidationError as exc:
                self.add_error("password", exc)
        if password and cleaned.get("password_confirm") and password != cleaned["password_confirm"]:
            self.add_error("password_confirm", _("Passwords do not match."))
        return cleaned


class UserProfileForm(forms.ModelForm):
    remove_avatar = forms.BooleanField(
        label=_("Remove current avatar"),
        required=False,
        widget=forms.CheckboxInput(
            attrs={
                "class": "profile-avatar-remove-input",
                "data-avatar-remove-input": "",
                "form": "profile-details-form",
            }
        ),
    )
    avatar_crop_x = forms.FloatField(
        required=False,
        min_value=0,
        widget=forms.HiddenInput(attrs={"form": "profile-details-form", "data-crop-x": ""}),
    )
    avatar_crop_y = forms.FloatField(
        required=False,
        min_value=0,
        widget=forms.HiddenInput(attrs={"form": "profile-details-form", "data-crop-y": ""}),
    )
    avatar_crop_size = forms.FloatField(
        required=False,
        min_value=1,
        widget=forms.HiddenInput(attrs={"form": "profile-details-form", "data-crop-size": ""}),
    )

    class Meta:
        model = UserProfile
        fields = ("display_name", "website", "avatar")
        labels = {
            "display_name": _("Display name"),
            "website": _("Personal website"),
            "avatar": _("Avatar"),
        }
        widgets = {
            "website": forms.URLInput(
                attrs={"placeholder": "https://example.com", "inputmode": "url"}
            ),
            "avatar": forms.FileInput(
                attrs={
                    "accept": ".jpg,.jpeg,.png,.gif,.webp",
                    "class": "profile-avatar-file-input",
                    "data-avatar-input": "",
                    "form": "profile-details-form",
                }
            ),
        }

    def clean_display_name(self):
        return self.cleaned_data["display_name"].strip()

    def clean(self):
        cleaned = super().clean()
        upload = cleaned.get("avatar")
        if not upload or getattr(upload, "_committed", False):
            return cleaned

        crop_values = (
            cleaned.get("avatar_crop_x"),
            cleaned.get("avatar_crop_y"),
            cleaned.get("avatar_crop_size"),
        )
        if all(value is None for value in crop_values):
            return cleaned
        if any(value is None for value in crop_values):
            self.add_error("avatar", _("Choose the avatar crop again."))
            return cleaned

        crop_x, crop_y, crop_size = crop_values
        try:
            upload.seek(0)
            image = ImageOps.exif_transpose(Image.open(upload))
            image.seek(0)
            width, height = image.size
            tolerance = 1.0
            if (
                crop_x < 0
                or crop_y < 0
                or crop_size <= 0
                or crop_x + crop_size > width + tolerance
                or crop_y + crop_size > height + tolerance
            ):
                raise ValueError("crop outside image")

            left = max(0, min(float(crop_x), width - 1))
            top = max(0, min(float(crop_y), height - 1))
            size = min(float(crop_size), width - left, height - top)
            cropped = image.crop((left, top, left + size, top + size))
            cropped = cropped.resize((512, 512), Image.Resampling.LANCZOS)
            has_alpha = "A" in cropped.getbands() or "transparency" in cropped.info
            if cropped.mode not in {"RGB", "RGBA"}:
                cropped = cropped.convert("RGBA" if has_alpha else "RGB")

            output = io.BytesIO()
            cropped.save(output, format="WEBP", quality=90, method=4)
            cleaned["avatar"] = SimpleUploadedFile(
                f"{Path(upload.name).stem or 'avatar'}.webp",
                output.getvalue(),
                content_type="image/webp",
            )
        except (OSError, SyntaxError, UnidentifiedImageError, ValueError):
            self.add_error("avatar", _("Choose the avatar crop again."))
        finally:
            upload.seek(0)
        return cleaned


class UserEmailChangeForm(forms.Form):
    email = forms.EmailField(label=_("Email"), max_length=254)
    current_password = forms.CharField(
        label=_("Current password"),
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        if not user.has_usable_password():
            self.fields.pop("current_password")
        self.fields["email"].initial = user.email

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if email.casefold() == (self.user.email or "").casefold():
            raise forms.ValidationError(_("Enter a different email address."))
        if User.objects.filter(email__iexact=email).exclude(pk=self.user.pk).exists():
            raise forms.ValidationError(_("This email address is already registered."))
        if (
            UserProfile.objects.filter(pending_email__iexact=email)
            .exclude(user=self.user)
            .exists()
        ):
            raise forms.ValidationError(
                _("This email address is awaiting confirmation for another account.")
            )
        return email

    def clean_current_password(self):
        password = self.cleaned_data["current_password"]
        if not self.user.check_password(password):
            raise forms.ValidationError(
                _("Enter your current password to change your email address.")
            )
        return password


class AccountDeletionForm(forms.Form):
    current_password = forms.CharField(
        label=_("Current password"),
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )
    username_confirmation = forms.CharField(label=_("Type your username to confirm"))

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        if not user.has_usable_password():
            self.fields.pop("current_password")

    def clean_current_password(self):
        password = self.cleaned_data["current_password"]
        if not self.user.check_password(password):
            raise forms.ValidationError(_("Your current password is incorrect."))
        return password

    def clean_username_confirmation(self):
        value = self.cleaned_data["username_confirmation"].strip()
        if value != self.user.get_username():
            raise forms.ValidationError(_("Enter your username exactly as shown."))
        return value

    def clean(self):
        cleaned = super().clean()
        if self.user.is_superuser and not type(self.user).objects.filter(
            is_superuser=True, is_active=True
        ).exclude(pk=self.user.pk).exists():
            raise forms.ValidationError(
                _("Create another active superuser before deleting this account.")
            )
        return cleaned
