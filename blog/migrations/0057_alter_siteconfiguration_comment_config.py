from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("blog", "0056_alter_siteconfiguration_comment_config")]

    operations = [
        migrations.AlterField(
            model_name="siteconfiguration",
            name="comment_config",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    "Use the original Redefine structure: {waline: {...}, "
                    "gitalk: {...}, twikoo: {...}, giscus: {...}}."
                ),
            ),
        ),
    ]
