from urllib.parse import unquote

from django.conf import settings
from django.db import migrations, models
from django.db.models import Count
import django.db.models.deletion
import django.utils.timezone


ARTICLE_PREFIX = "/article/"


def seed_article_view_counts(apps, schema_editor):
    database = schema_editor.connection.alias
    Article = apps.get_model("blog", "ArticleModel")
    Traffic = apps.get_model("blog", "TrafficModel")
    rows = (
        Traffic.objects.using(database).filter(
            path__startswith=ARTICLE_PREFIX,
            path__endswith="/",
        )
        .values("path")
        .annotate(total=Count("id"))
    )
    for row in rows.iterator():
        slug = unquote(row["path"][len(ARTICLE_PREFIX):-1])
        if slug:
            Article.objects.using(database).filter(slug=slug).update(
                view_count=row["total"]
            )


def reset_article_view_counts(apps, schema_editor):
    apps.get_model("blog", "ArticleModel").objects.using(
        schema_editor.connection.alias
    ).update(view_count=0)


class Migration(migrations.Migration):
    dependencies = [("blog", "0003_menulinktranslation")]

    operations = [
        migrations.AddField(
            model_name="siteconfiguration",
            name="updated_at",
            field=models.DateTimeField(
                auto_now=True,
                default=django.utils.timezone.now,
                editable=False,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="articlemodel",
            name="view_count",
            field=models.PositiveBigIntegerField(default=0, editable=False),
        ),
        migrations.RunPython(
            seed_article_view_counts,
            reset_article_view_counts,
        ),
        migrations.CreateModel(
            name="PendingRegistration",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pending_registration",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ("created_at",)},
        ),
        migrations.AddField(
            model_name="userprofile",
            name="website",
            field=models.URLField(blank=True, verbose_name="personal website"),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="pending_website",
            field=models.URLField(
                blank=True, verbose_name="pending personal website"
            ),
        ),
    ]
