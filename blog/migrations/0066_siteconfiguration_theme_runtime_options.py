from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("blog", "0065_category_parent"),
    ]

    operations = [
        migrations.AddField(
            model_name="siteconfiguration",
            name="article_lazyload",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="siteconfiguration",
            name="article_pangu_js",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="siteconfiguration",
            name="navbar_search_preload",
            field=models.BooleanField(default=True),
        ),
    ]
