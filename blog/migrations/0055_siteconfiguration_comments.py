from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("blog", "0054_friendcategory_friendlink")]

    operations = [
        migrations.AddField(
            model_name="siteconfiguration",
            name="comment_system",
            field=models.CharField(
                blank=True,
                choices=[
                    ("waline", "Waline"),
                    ("gitalk", "Gitalk"),
                    ("twikoo", "Twikoo"),
                    ("giscus", "Giscus"),
                ],
                default="",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="siteconfiguration",
            name="comment_config",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
