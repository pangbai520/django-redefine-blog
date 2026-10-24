from django.db import migrations, models


def restore_title_fallback(apps, schema_editor):
    SiteConfiguration = apps.get_model("blog", "SiteConfiguration")
    SiteConfiguration.objects.filter(preloader_message="Loading...").update(
        preloader_message=""
    )


class Migration(migrations.Migration):
    dependencies = [
        ("blog", "0078_rewrite_legacy_theme_identity_defaults"),
    ]

    operations = [
        migrations.RunPython(restore_title_fallback, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="siteconfiguration",
            name="preloader_message",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
    ]
