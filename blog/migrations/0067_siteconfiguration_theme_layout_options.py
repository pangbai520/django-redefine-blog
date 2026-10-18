from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("blog", "0066_siteconfiguration_theme_runtime_options"),
    ]

    operations = [
        migrations.AddField(
            model_name="siteconfiguration",
            name="article_font_size",
            field=models.PositiveIntegerField(default=16, help_text="px"),
        ),
        migrations.AddField(
            model_name="siteconfiguration",
            name="article_image_border_radius",
            field=models.PositiveIntegerField(default=14, help_text="px"),
        ),
        migrations.AddField(
            model_name="siteconfiguration",
            name="article_line_height",
            field=models.FloatField(default=1.5),
        ),
        migrations.AddField(
            model_name="siteconfiguration",
            name="content_max_width",
            field=models.PositiveIntegerField(default=1000, help_text="px"),
        ),
        migrations.AddField(
            model_name="siteconfiguration",
            name="heading_h1_top_spacing",
            field=models.FloatField(default=3.2, help_text="rem"),
        ),
        migrations.AddField(
            model_name="siteconfiguration",
            name="heading_h2_top_spacing",
            field=models.FloatField(default=2.4, help_text="rem"),
        ),
        migrations.AddField(
            model_name="siteconfiguration",
            name="heading_h3_top_spacing",
            field=models.FloatField(default=1.9, help_text="rem"),
        ),
        migrations.AddField(
            model_name="siteconfiguration",
            name="heading_h4_top_spacing",
            field=models.FloatField(default=1.6, help_text="rem"),
        ),
        migrations.AddField(
            model_name="siteconfiguration",
            name="heading_h5_top_spacing",
            field=models.FloatField(default=1.4, help_text="rem"),
        ),
        migrations.AddField(
            model_name="siteconfiguration",
            name="heading_h6_top_spacing",
            field=models.FloatField(default=1.3, help_text="rem"),
        ),
        migrations.AddField(
            model_name="siteconfiguration",
            name="navbar_width_home",
            field=models.PositiveIntegerField(default=1200, help_text="px"),
        ),
        migrations.AddField(
            model_name="siteconfiguration",
            name="navbar_width_pages",
            field=models.PositiveIntegerField(default=1000, help_text="px"),
        ),
        migrations.AddField(
            model_name="siteconfiguration",
            name="toc_sidebar_width",
            field=models.PositiveIntegerField(default=210, help_text="px"),
        ),
        migrations.AlterField(
            model_name="siteconfiguration",
            name="codeblock_dark",
            field=models.CharField(
                choices=[
                    ("github-dark", "GitHub Dark"),
                    ("monokai-sublime", "Monokai Sublime"),
                    ("vs2015", "VS2015"),
                    ("night-owl", "Night Owl"),
                    ("atom-one-dark", "Atom One Dark"),
                    ("nord", "Nord"),
                    ("tokyo-night-dark", "Tokyo Night Dark"),
                    ("a11y-dark", "A11y Dark"),
                    ("agate", "Agate"),
                ],
                default="vs2015",
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name="siteconfiguration",
            name="counter_enabled",
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name="siteconfiguration",
            name="friends_page_columns",
            field=models.PositiveIntegerField(
                choices=[(2, "2 Column"), (3, "3 Column")], default=2
            ),
        ),
        migrations.AlterField(
            model_name="siteconfiguration",
            name="homebanner_style",
            field=models.CharField(
                choices=[("static", "Static"), ("fixed", "Fixed")],
                default="fixed",
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name="siteconfiguration",
            name="show_reading_time",
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name="siteconfiguration",
            name="show_word_counter",
            field=models.BooleanField(default=True),
        ),
    ]
