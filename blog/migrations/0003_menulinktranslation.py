import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("blog", "0002_siteconfiguration_friends_enabled"),
    ]

    operations = [
        migrations.AlterField(
            model_name="menulink",
            name="name",
            field=models.CharField(
                help_text=(
                    "默认名称（通常填写英文）。About、Archives 等标准名称会自动翻译；"
                    "自定义名称可在保存后进入此链接配置各语言翻译。"
                ),
                max_length=50,
                verbose_name="默认显示名称",
            ),
        ),
        migrations.CreateModel(
            name="MenuLinkTranslation",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "language_code",
                    models.CharField(max_length=16, verbose_name="语言代码"),
                ),
                ("name", models.CharField(max_length=50, verbose_name="显示名称")),
                (
                    "menu_link",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="translations",
                        to="blog.menulink",
                        verbose_name="菜单链接",
                    ),
                ),
            ],
            options={
                "verbose_name": "菜单链接翻译",
                "verbose_name_plural": "菜单链接翻译",
                "ordering": ("language_code",),
                "constraints": [
                    models.UniqueConstraint(
                        fields=("menu_link", "language_code"),
                        name="unique_menu_link_language",
                    )
                ],
            },
        ),
    ]
