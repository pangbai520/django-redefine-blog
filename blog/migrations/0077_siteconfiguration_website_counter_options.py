from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("blog", "0076_articlesearchdocument"),
    ]

    operations = [
        migrations.AddField(
            model_name="siteconfiguration",
            name="website_counter_enabled",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="siteconfiguration",
            name="website_counter_post_pv",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="siteconfiguration",
            name="website_counter_site_pv",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="siteconfiguration",
            name="website_counter_site_uv",
            field=models.BooleanField(default=True),
        ),
    ]
