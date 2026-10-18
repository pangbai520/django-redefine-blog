from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from .models import ArticleModel


class ArticleSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        return ArticleModel.objects.published().order_by("-created_at")

    def lastmod(self, article):
        return article.updated_at


class StaticPageSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.5

    def items(self):
        return ("index", "archives", "categories", "tags", "friends")

    def location(self, name):
        return reverse(name)
