from django.db import migrations, models
import django.utils.translation


class Migration(migrations.Migration):
    dependencies = [("blog", "0006_standalone_pages_and_badge_translations")]

    operations = [
        migrations.AlterField(
            model_name="standalonepagetranslation",
            name="title",
            field=models.CharField(
                blank=True,
                max_length=200,
                verbose_name=django.utils.translation.gettext_lazy(
                    "translated page title"
                ),
            ),
        ),
    ]
