from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("blog", "0021_articleratingemoji_and_more")]

    operations = [
        migrations.AddField(
            model_name="siteconfiguration",
            name="comment_page_size",
            field=models.PositiveSmallIntegerField(
                default=10,
                help_text=(
                    "Number of top-level comment threads loaded initially and each "
                    "time visitors choose Load more."
                ),
                validators=[MinValueValidator(1), MaxValueValidator(100)],
                verbose_name="Comments per load",
            ),
        ),
    ]
