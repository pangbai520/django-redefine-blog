from django.conf import settings
from django.core.cache import cache
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import models
from django.utils.translation import get_language, gettext_lazy as _

CACHE_KEY = "actived_site_config"


class MenuLink(models.Model):
    LOCATION_CHOICES = [
        ("navbar", "顶部导航栏"),
        ("sidebar", "侧边栏菜单"),
        ("social", "首页右下角社交链接"),
        ("qrs", "社交二维码卡片"),
    ]

    active_namespace = models.CharField(max_length=100, blank=True)

    config = models.ForeignKey(
        "blog.SiteConfiguration",
        on_delete=models.CASCADE,
        related_name="links",
    )
    link_location = models.CharField(
        "部署位置", max_length=20, choices=LOCATION_CHOICES
    )
    name = models.CharField(
        "默认显示名称",
        max_length=50,
        help_text=(
            "默认名称（通常填写英文）。About、Archives 等标准名称会自动翻译；"
            "自定义名称可在保存后进入此链接配置各语言翻译。"
        ),
    )
    url = models.CharField(
        "链接地址/路径", max_length=255, help_text="外部链接填 http，内部路径填 /"
    )
    icon = models.CharField(
        "图标类名",
        max_length=100,
        blank=True,
        help_text=(
            "FontAwesome 类名，例如：fa-solid fa-house 或 " "fa-brands fa-github"
        ),
    )

    # allow nesting only where the navbar can render a dropdown
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="submenus",
        verbose_name="父级菜单",
    )
    order = models.PositiveIntegerField(
        "排序权重", default=0, help_text="数字越小越靠前"
    )

    @property
    def inferred_namespace(self):
        if self.active_namespace:
            return self.active_namespace

        if self.url == "/":
            return "index"

        # reduce detail URLs such as /tags/name to their top-level section
        if self.url and self.url.startswith("/"):
            return self.url.strip("/").split("/")[0]

        return None

    def is_active(self, request):
        match = request.resolver_match
        if not match:
            return False

        # use the resolved namespace first; it survives URL-prefix changes
        if self.inferred_namespace and match.app_name:
            return match.app_name == self.inferred_namespace

        # project-level routes may have no app namespace, so use the view name as fallback
        if self.inferred_namespace and match.view_name:
            return match.view_name.startswith(self.inferred_namespace)

        return False

    @staticmethod
    def _lang_code(language_code):
        code = (language_code or "").strip().lower().replace("_", "-")
        aliases = {
            "zh-cn": "zh-hans",
            "zh-sg": "zh-hans",
            "zh-hant": "zh-tw",
            "zh-mo": "zh-hk",
        }
        return aliases.get(code, code)

    def resolve_localized_name(self, language_code=None):
        """Return ``(label, is_explicit_translation)`` for the active language."""
        code = self._lang_code(language_code or get_language())
        if not code or code == "en" or code.startswith("en-"):
            return self.name, False

        candidates = [code]
        base_code = code.split("-", 1)[0]
        if base_code in {"es", "fr", "ja"} and base_code not in candidates:
            candidates.append(base_code)

        prefetched = getattr(self, "_prefetched_objects_cache", {}).get("translations")
        if prefetched is None:
            translations = self.translations.filter(language_code__in=candidates)
        else:
            translations = prefetched

        translations_by_code = {
            item.language_code: item.name
            for item in translations
            if item.language_code in candidates
        }
        for candidate in candidates:
            if candidate in translations_by_code:
                return translations_by_code[candidate], True

        return self.name, False

    @property
    def has_submenus(self):
        """Return whether this navigation item has children."""
        return self.submenus.exists()

    @property
    def link_type(self):
        """Classify the link for social-link rendering."""
        name = self.name.lower()

        if name == "email":
            return "email"
        elif name.startswith("fa-"):
            return "fa"
        elif name.startswith("/") or name.startswith("http"):
            return "img"
        else:
            return "fa-default"

    @property
    def href(self):
        """Return the final href, including the mailto scheme when needed."""
        try:
            return self._safe_url()
        except ValidationError:
            # Old rows and bulk imports may have bypassed model validation.
            # Rendering them as a no-op keeps unsafe schemes out of templates.
            return "#"

    @property
    def social_icon_class(self):
        """Return the Font Awesome class used by social links."""
        if self.link_type == "fa-default":
            return f"fa-{self.name}"
        return self.name

    @property
    def qr_type(self):
        """Classify a QR-code entry as an icon, image, or brand."""
        key = self.name
        if "fa-" in key:
            return "fa"
        elif key.startswith("/") or key.startswith("http"):
            return "img"
        else:
            return "brand"

    @property
    def qr_img(self):
        """Return the QR image URL."""
        try:
            return self._safe_url(allow_email=False)
        except ValidationError:
            return ""

    @property
    def qr_icon_class(self):
        """Return the icon class for a brand QR entry."""
        if self.qr_type == "brand":
            return f"fa-{self.name}"
        return self.name

    @property
    def user_icon(self):
        """Return the explicit icon or infer one from the link name."""
        if self.icon:
            return self.icon

        name_lower = self.name.lower()
        if name_lower.startswith("fa-"):
            return name_lower

        return f"fa-solid fa-{name_lower}"

    class Meta:
        verbose_name = "Integrated link"
        verbose_name_plural = verbose_name
        ordering = ["order"]

    def _safe_url(self, *, allow_email=True):
        value = (self.url or "").strip()
        if not value:
            return "#"
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValidationError({"url": _("Enter a valid website URL.")})

        if allow_email and self.link_type == "email":
            address = value[7:] if value.lower().startswith("mailto:") else value
            try:
                validate_email(address)
            except ValidationError as exc:
                raise ValidationError(
                    {"url": _("Enter a valid email address.")}
                ) from exc
            return f"mailto:{address}"

        if value.startswith(("/", "#", "?")):
            if value.startswith("//"):
                raise ValidationError({"url": _("Enter a valid website URL.")})
            return value

        parsed = urlsplit(value)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            raise ValidationError({"url": _("Enter a valid website URL.")})
        if parsed.username or parsed.password:
            raise ValidationError({"url": _("Enter a valid website URL.")})
        return value

    def clean(self):
        super().clean()
        self.url = (self.url or "").strip()
        self._safe_url()

        # only the navbar renders nested links
        if self.parent and self.link_location != "navbar":
            raise ValidationError(
                {
                    "parent": f"位置为 '{self.get_link_location_display()}' 的链接不允许设置父级菜单。"
                }
            )

        # a child in another location would never appear under its parent
        if self.parent and self.parent.link_location != self.link_location:
            raise ValidationError("子菜单的位置必须与父级菜单一致。")

        # only navbar and sidebar templates read this icon field
        if self.icon and self.link_location not in ["navbar", "sidebar"]:
            raise ValidationError(
                {
                    "icon": (
                        "只有位置为 '顶部导航栏' 或 '侧边栏菜单' 时才允许填写图标。"
                        f"当前位置 '{self.get_link_location_display()}' 请保持此项为空，"
                        "若需要 Font Awesome，请在名称一栏中输入。"
                    )
                }
            )

        if self.parent and self.parent_id == self.id:
            raise ValidationError({"parent": "父级菜单不能是菜单本身。"})

        if self.parent and self.icon:
            raise ValidationError(
                {"icon": f"链接 '{self.name}' 是子菜单，子菜单不允许设置图标。"}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[{self.get_link_location_display()}] {self.name}"


class MenuLinkTranslation(models.Model):
    menu_link = models.ForeignKey(
        MenuLink,
        on_delete=models.CASCADE,
        related_name="translations",
        verbose_name="菜单链接",
    )
    language_code = models.CharField("语言代码", max_length=16)
    name = models.CharField("显示名称", max_length=50)

    class Meta:
        ordering = ("language_code",)
        constraints = (
            models.UniqueConstraint(
                fields=("menu_link", "language_code"),
                name="unique_menu_link_language",
            ),
        )
        verbose_name = "菜单链接翻译"
        verbose_name_plural = "菜单链接翻译"

    def __str__(self):
        language_name = dict(settings.LANGUAGES).get(
            self.language_code, self.language_code
        )
        return f"{self.menu_link.name} ({language_name})"

    def clean(self):
        supported_languages = {
            code for code, _name in settings.LANGUAGES if code != "en"
        }
        if self.language_code not in supported_languages:
            raise ValidationError({"language_code": "请选择网站当前支持的非英语语言。"})


class Font(models.Model):
    FONT_TYPE_CHOICES = [
        ("code_block", "Code Block"),
        ("home_banner", "Home Banner"),
        ("global", "Global"),
        ("chinese", "Chinese"),
        ("english", "English"),
        ("title", "Title"),
    ]

    config = models.ForeignKey(
        "blog.SiteConfiguration",
        on_delete=models.CASCADE,
        related_name="fonts",
    )
    type = models.CharField(max_length=20, choices=FONT_TYPE_CHOICES)
    enabled = models.BooleanField(default=False)
    family = models.CharField(max_length=100, blank=True)
    url = models.URLField(blank=True)

    class Meta:
        verbose_name = "Font"
        verbose_name_plural = "Fonts"

    def __str__(self):
        return (
            f"{self.get_type_display()} ({'enabled' if self.enabled else 'disabled'})"
        )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        cache.delete(CACHE_KEY)

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        cache.delete(CACHE_KEY)
