from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("blog", "0079_restore_preloader_title_fallback"),
    ]

    operations = [
        migrations.AlterField(
            model_name="siteconfiguration",
            name="article_dateformat",
            field=models.CharField(
                default="auto",
                help_text=(
                    "Use auto, relative, or a Moment.js-style format such as "
                    "YYYY-MM-DD, YYYY/MM/DD HH:mm, or MMM D, YYYY."
                ),
                max_length=50,
            ),
        ),
    ]
