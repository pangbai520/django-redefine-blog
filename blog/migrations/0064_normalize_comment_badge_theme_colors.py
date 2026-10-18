from django.db import migrations


def restore_theme_default(apps, schema_editor):
    CommentBadge = apps.get_model("blog", "CommentBadge")
    CommentBadge.objects.filter(color="#3498db").update(color="")


class Migration(migrations.Migration):
    dependencies = [("blog", "0063_commentbadgeassignment_color_override")]

    operations = [migrations.RunPython(restore_theme_default, migrations.RunPython.noop)]
