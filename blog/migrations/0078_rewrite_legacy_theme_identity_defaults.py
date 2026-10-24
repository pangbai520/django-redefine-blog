from django.db import migrations, models


def rewrite_legacy_defaults(apps, schema_editor):
    SiteConfiguration = apps.get_model("blog", "SiteConfiguration")
    replacements = (
        ("site_name", "Theme Redefine", "Django Redefine"),
        (
            "site_subname",
            "Redefine Your Hexo Journey.",
            "Redefine Your Django Journey.",
        ),
        ("hb_title", "Theme Redefine", "Django Redefine"),
        (
            "og_description",
            "Hexo Theme Redefine, Redefine Your Hexo Journey.",
            "Django Redefine, Redefine Your Django Journey.",
        ),
        (
            "site_description",
            "A Django blog based on Theme Redefine",
            "A Django blog based on Redefine.",
        ),
    )
    for field_name, old_value, new_value in replacements:
        SiteConfiguration.objects.filter(**{field_name: old_value}).update(
            **{field_name: new_value}
        )


class Migration(migrations.Migration):
    dependencies = [
        ("blog", "0077_siteconfiguration_website_counter_options"),
    ]

    operations = [
        migrations.RunPython(rewrite_legacy_defaults, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="siteconfiguration",
            name="hb_title",
            field=models.CharField(default="Django Redefine", max_length=100),
        ),
        migrations.AlterField(
            model_name="siteconfiguration",
            name="og_description",
            field=models.CharField(
                blank=True,
                default="Django Redefine, Redefine Your Django Journey.",
                max_length=200,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="siteconfiguration",
            name="site_name",
            field=models.CharField(
                default="Django Redefine",
                max_length=200,
                verbose_name="site name",
            ),
        ),
        migrations.AlterField(
            model_name="siteconfiguration",
            name="site_subname",
            field=models.CharField(
                blank=True,
                default="Redefine Your Django Journey.",
                max_length=200,
                null=True,
                verbose_name="site info subtitle",
            ),
        ),
    ]
