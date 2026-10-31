from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("blog", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="siteconfiguration",
            name="friends_enabled",
            field=models.BooleanField(default=True),
        ),
    ]
