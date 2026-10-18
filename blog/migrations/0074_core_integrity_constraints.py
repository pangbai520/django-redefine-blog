from django.db import migrations, models
from django.db.models import Q


def normalize_constrained_rows(apps, schema_editor):
    SiteConfiguration = apps.get_model("blog", "SiteConfiguration")
    active = list(SiteConfiguration.objects.filter(is_active=True).order_by("pk"))
    if len(active) > 1:
        SiteConfiguration.objects.filter(pk__in=[item.pk for item in active[1:]]).update(
            is_active=False
        )

    Comment = apps.get_model("blog", "Comment")
    article_ids = (
        Comment.objects.filter(is_sticky=True)
        .values_list("article_id", flat=True)
        .order_by()
        .distinct()
    )
    for article_id in article_ids:
        sticky_ids = list(
            Comment.objects.filter(article_id=article_id, is_sticky=True)
            .order_by("-created_at", "-pk")
            .values_list("pk", flat=True)
        )
        if len(sticky_ids) > 1:
            Comment.objects.filter(pk__in=sticky_ids[1:]).update(is_sticky=False)


class Migration(migrations.Migration):
    dependencies = [
        ("blog", "0073_commentimage"),
    ]

    operations = [
        migrations.RunPython(normalize_constrained_rows, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="siteconfiguration",
            constraint=models.UniqueConstraint(
                condition=Q(is_active=True),
                fields=("is_active",),
                name="unique_active_site_configuration",
            ),
        ),
        migrations.AddConstraint(
            model_name="comment",
            constraint=models.UniqueConstraint(
                condition=Q(is_sticky=True),
                fields=("article",),
                name="unique_sticky_comment_per_article",
            ),
        ),
    ]
