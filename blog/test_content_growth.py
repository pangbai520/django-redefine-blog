from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import ArticleModel, ArticleSearchDocument, Category, SiteConfiguration, Tag
from .recommendations import related_articles
from .search import rebuild_vendor_index, search_articles


class ContentGrowthTests(TestCase):
    def setUp(self):
        cache.clear()
        self.site = SiteConfiguration.objects.create(
            config_name="Growth",
            site_name="Growth Blog",
            is_active=True,
            navbar_search_enabled=True,
        )

    def create_article(self, title, content, **overrides):
        values = {
            "title": title,
            "content": content,
            "is_published": True,
            "created_at": timezone.now() - timedelta(minutes=1),
        }
        values.update(overrides)
        return ArticleModel.objects.create(**values)

    def test_mysql_index_ddl_is_deferred_inside_an_atomic_block(self):
        with patch("blog.search.connection") as database:
            database.vendor = "mysql"
            database.in_atomic_block = True

            self.assertEqual(rebuild_vendor_index(), "database-fallback")
            database.cursor.assert_not_called()

    def test_server_search_is_bounded_and_excludes_non_public_articles(self):
        visible = self.create_article("Search target", "A distinctive pangbai phrase")
        self.create_article("Draft target", "distinctive pangbai phrase", is_published=False)
        self.create_article(
            "Scheduled target",
            "distinctive pangbai phrase",
            created_at=timezone.now() + timedelta(days=1),
        )

        response = self.client.get(reverse("search_data"), {"q": "distinctive"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([item["url"] for item in payload["results"]], [visible.get_absolute_url()])
        self.assertIn(payload["backend"], {
            "database-fallback",
            "sqlite-fts5",
            "mysql-fulltext",
            "postgresql-search-vector",
        })
        self.assertEqual(self.client.get(reverse("search_data")).json()["results"], [])

    def test_search_document_and_cached_query_follow_article_changes(self):
        article = self.create_article("Mutable", "beforeword")
        self.assertTrue(ArticleSearchDocument.objects.filter(article=article).exists())
        self.assertEqual(len(search_articles("beforeword")[0]), 1)

        article.content = "afterword"
        article.save()

        self.assertEqual(search_articles("beforeword")[0], [])
        self.assertEqual(len(search_articles("afterword")[0]), 1)

        article_id = article.pk
        article.delete()
        self.assertFalse(ArticleSearchDocument.objects.filter(article_id=article_id).exists())
        self.assertEqual(search_articles("afterword")[0], [])

    def test_server_search_handles_continuous_chinese_text(self):
        article = self.create_article("中文检索", "这里包含一段连续的数据库搜索内容")

        results, _ = search_articles("数据库搜索")

        self.assertEqual([item["url"] for item in results], [article.get_absolute_url()])

    def test_rebuild_search_index_command_indexes_existing_content(self):
        article = self.create_article("Indexed", "rebuildable body")
        ArticleSearchDocument.objects.all().delete()
        output = StringIO()

        call_command("rebuild_search_index", stdout=output)

        self.assertTrue(ArticleSearchDocument.objects.filter(article=article).exists())
        self.assertIn(f"Indexed {ArticleModel.objects.count()} articles using", output.getvalue())
        self.assertEqual(len(search_articles("rebuildable")[0]), 1)

    def test_markdown_rendering_is_reused_across_model_instances(self):
        article = self.create_article("Cached Markdown", "## Cached heading")
        rendered = str(article.html_content)
        fresh_instance = ArticleModel.objects.get(pk=article.pk)

        with patch("blog.models.Markdown.convert", side_effect=AssertionError("rendered twice")):
            cached_render = str(fresh_instance.html_content)

        self.assertEqual(cached_render, rendered)

    def test_content_cache_is_invalidated_for_archives_feed_and_sitemap(self):
        first = self.create_article("First cached article", "First")
        text_endpoints = (reverse("archives"), reverse("article_feed"))
        sitemap_endpoint = reverse("django.contrib.sitemaps.views.sitemap")
        for endpoint in text_endpoints:
            self.assertContains(self.client.get(endpoint), first.title)
        self.assertContains(self.client.get(sitemap_endpoint), first.get_absolute_url())

        second = self.create_article("Second cached article", "Second")

        for endpoint in text_endpoints:
            self.assertContains(self.client.get(endpoint), second.title)
        self.assertContains(self.client.get(sitemap_endpoint), second.get_absolute_url())

    def test_related_articles_prioritize_shared_taxonomy(self):
        category = Category.objects.create(name="Django", slug="django")
        tag = Tag.objects.create(name="Search", slug="search")
        source = self.create_article("Source", "Source")
        closest = self.create_article("Closest", "Closest")
        category_only = self.create_article("Category only", "Category")
        self.create_article("Unrelated", "Unrelated")
        source.category.add(category)
        source.tags.add(tag)
        closest.category.add(category)
        closest.tags.add(tag)
        category_only.category.add(category)

        recommendations = related_articles(source, 3)

        self.assertEqual(recommendations[0], closest)
        self.assertEqual(recommendations[1], category_only)
