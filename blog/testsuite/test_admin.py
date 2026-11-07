import json
from django.contrib.auth import get_user_model
from django.forms.models import model_to_dict
from django.test import TestCase, override_settings
from django.urls import reverse

from ..admin import (
    ArticleAdmin,
    FriendCategoryAdmin,
    SiteConfigurationAdmin,
    SiteConfigurationForm,
)
from ..models import Category, EditorImage, SiteConfiguration, Tag

User = get_user_model()


class NotFoundPageTests(TestCase):
    @override_settings(DEBUG=False)
    def test_unknown_page(self):
        SiteConfiguration.objects.create(
            config_name="404 theme",
            site_name="Test site",
            is_active=True,
        )
        response = self.client.get("/route-that-does-not-exist/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Page Not Found", status_code=404)
        self.assertContains(response, "nf-container", status_code=404)


class AdminExperienceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            "dashboard-admin",
            "admin@example.com",
            "A-strong-password-123",
        )
        self.site = SiteConfiguration.objects.create(
            config_name="Admin theme",
            site_name="Admin test site",
            is_active=True,
        )
        self.client.force_login(self.user)

    def configuration_form_data(self, **updates):
        data = model_to_dict(self.site)
        for field_name in (
            "subtitle_text",
            "author_label_list",
            "recommendation_skip_dirs",
            "aplayer_config",
        ):
            data[field_name] = json.dumps(data[field_name])
        data.update(
            {
                "waline_emoji": "[]",
                "waline_reaction": "[]",
            }
        )
        data.update(updates)
        return data

    def test_site_field(self):
        visible = set()
        for _, options in SiteConfigurationAdmin.fieldsets:
            for item in options.get("fields", ()):
                visible.update(item if isinstance(item, (tuple, list)) else (item,))

        editable = {
            field.name
            for field in SiteConfiguration._meta.fields
            if field.editable and not field.auto_created
        }
        self.assertEqual(
            editable - visible,
            {
                "comment_config",
                "navbar_search_preload",
                "bookmarks_enabled",
                "essays_enabled",
                "masonry_enabled",
                "friends_enabled",
                "friends_page_columns",
                "tags_page_style",
            },
        )

    def test_admin_workflows(self):
        self.assertEqual(
            SiteConfigurationAdmin.list_filter, ("is_active", "comment_system")
        )
        self.assertEqual(
            ArticleAdmin.list_filter,
            ("is_published", "created_at", "category", "tags"),
        )
        self.assertEqual(FriendCategoryAdmin.list_filter, ())

    def test_taxonomy_slugs(self):
        category = Category.objects.create(name="编程语言")
        tag = Tag.objects.create(name="Python Tricks")

        self.assertEqual(category.slug, "编程语言")
        self.assertEqual(tag.slug, "python-tricks")

    def test_article_taxonomy(self):
        response = self.client.get(reverse("admin:blog_articlemodel_add"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="selectfilter"', count=2)
        self.assertNotContains(response, 'type="checkbox" name="category"')
        self.assertNotContains(response, 'type="checkbox" name="tags"')

    def test_image_delete(self):
        image = EditorImage.objects.create(
            image="content-images/test.png",
            digest="a" * 64,
            original_name="test.png",
        )

        response = self.client.get(reverse("admin:blog_editorimage_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse("admin:blog_editorimage_delete", args=(image.pk,)),
        )
        delete_page = self.client.get(
            reverse("admin:blog_editorimage_delete", args=(image.pk,))
        )
        self.assertEqual(delete_page.status_code, 200)

    def test_admin_default(self):
        response = self.client.get(reverse("admin:blog_siteconfiguration_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<details data-filter-title="comment system">')
        self.assertNotContains(
            response, '<details data-filter-title="comment system" open>'
        )
        self.assertNotContains(response, "homebanner enabled")
        self.assertNotContains(response, "comment enabled")

    def test_comment_save(self):
        form = SiteConfigurationForm(
            data=self.configuration_form_data(
                comment_enabled=True,
                comment_system="waline",
                waline_server_url="",
                waline_emoji='{"not": "an array"}',
            ),
            instance=self.site,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("waline_server_url", form.errors)
        self.assertIn("waline_emoji", form.errors)

    def test_switching_settings(self):
        self.site.comment_config = {
            "gitalk": {"repo": "preserved-repository"},
            "waline": {"serverUrl": "https://old.example.com"},
        }
        self.site.save()
        form = SiteConfigurationForm(
            data=self.configuration_form_data(
                comment_enabled=True,
                comment_system="waline",
                waline_server_url="https://comments.example.com",
            ),
            instance=self.site,
        )

        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(saved.comment_config["gitalk"]["repo"], "preserved-repository")
        self.assertEqual(
            saved.comment_config["waline"]["serverUrl"], "https://comments.example.com"
        )

    def test_admin_render(self):
        self.site.colour_primary = "#245678"
        self.site.save(update_fields=("colour_primary",))
        dashboard = self.client.get(reverse("admin:index"))
        configuration = self.client.get(
            reverse("admin:blog_siteconfiguration_change", args=(self.site.pk,))
        )

        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, "redefine-dashboard-summary")
        self.assertContains(dashboard, "Visits today")
        self.assertNotContains(dashboard, "CONTROL CENTER")
        self.assertContains(dashboard, "css/admin/redefine-admin.css")
        self.assertContains(dashboard, "--redefine-admin-accent: #245678;")
        self.assertEqual(configuration.status_code, 200)
        self.assertContains(configuration, "js/admin/redefine-admin.js")
        self.assertContains(configuration, "Edit site configuration")
        self.assertContains(configuration, "Configuration")
        self.assertNotContains(configuration, "📂")
        self.assertContains(configuration, "recommendation_mobile_limit")
        self.assertContains(configuration, "sidetools_auto_expand")
