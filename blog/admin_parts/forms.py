from django.forms.models import BaseInlineFormSet
from django.utils.translation import gettext_lazy as _


class UniqueLanguageInlineFormSet(BaseInlineFormSet):
    duplicate_message = _("Each language can only be added once.")

    def clean(self):
        super().clean()
        languages = set()
        for form in self.forms:
            data = getattr(form, "cleaned_data", None) or {}
            if data.get("DELETE"):
                continue

            lang = data.get("language_code")
            if not lang:
                continue

            lang = lang.replace("_", "-").lower()
            if lang in languages:
                form.add_error("language_code", self.duplicate_message)
            languages.add(lang)
