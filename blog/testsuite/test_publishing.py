from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ..models import (
    ArticleModel,
    Category,
    Tag,
    TrafficModel,
)

User = get_user_model()


class CorePublishingTests(TestCase):
    def test_future_time(self):
        baseline_words = self.client.get(reverse("index")).context["total_words"]
        category = Category.objects.create(
            name="Scheduled category", slug="scheduled-category"
        )
        tag = Tag.objects.create(name="Scheduled tag", slug="scheduled-tag")
        article = ArticleModel.objects.create(
            title="Scheduled article",
            content="Not public yet",
            is_published=True,
            created_at=timezone.now() + timedelta(days=1),
        )
        article.category.add(category)
        article.tags.add(tag)

        self.assertFalse(
            ArticleModel.objects.published().filter(pk=article.pk).exists()
        )
        self.assertEqual(self.client.get(article.get_absolute_url()).status_code, 404)
        index_response = self.client.get(reverse("index"))
        self.assertNotContains(index_response, article.title)
        self.assertEqual(index_response.context["total_words"], baseline_words)
        self.assertNotContains(
            self.client.get(reverse("search_data"), {"q": "Scheduled"}),
            article.title,
        )
        self.assertNotContains(self.client.get(reverse("categories")), category.name)
        self.assertNotContains(self.client.get(reverse("tags")), tag.name)

    def test_editing_slug(self):
        article = ArticleModel.objects.create(
            title="Original title",
            content="Body",
            is_published=True,
        )
        original_slug = article.slug

        article.title = "Renamed title"
        article.save()
        article.refresh_from_db()

        self.assertEqual(article.slug, original_slug)

    def test_content_counters(self):
        article = ArticleModel.objects.create(title="Counters", content="one")
        original_count = article.word_counter

        article.content = "one two three four"
        article.save(update_fields=("content",))
        article.refresh_from_db()

        self.assertGreater(article.word_counter, original_count)
        self.assertGreaterEqual(article.reading_time, 1)

    def test_category_rejected(self):
        parent = Category.objects.create(name="Parent", slug="parent")
        child = Category.objects.create(name="Child", slug="child", parent=parent)
        parent.parent = child

        with self.assertRaises(ValidationError):
            parent.full_clean()

    def test_article_caches(self):
        cache.set("total_word_count", 1)
        cache.set("site_stats_counts", {"articles_count": 1})
        article = ArticleModel.objects.create(
            title="Cache invalidation",
            content="Body",
            is_published=True,
        )

        self.assertIsNone(cache.get("total_word_count"))
        self.assertIsNone(cache.get("site_stats_counts"))

        cache.set("site_stats_counts", {"tags_count": 0})
        tag = Tag.objects.create(name="Cache", slug="cache")
        article.tags.add(tag)
        self.assertIsNone(cache.get("site_stats_counts"))

        cache.set("site_traffic", {"site_pv": 1})
        TrafficModel.objects.create(path="/", ip="192.0.2.20", user_agent="Browser")
        self.assertIsNone(cache.get("site_traffic"))
