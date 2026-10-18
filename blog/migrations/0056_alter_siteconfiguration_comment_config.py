from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("blog", "0055_siteconfiguration_comments")]

    operations = [
        migrations.AlterField(
            model_name="siteconfiguration",
            name="comment_config",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    "Provider settings as JSON. Waline: server_url; Gitalk: "
                    "client_id, client_secret, owner, repo; Twikoo: server_url; "
                    "Giscus: repo, repo_id, category, category_id."
                ),
            ),
        ),
    ]
