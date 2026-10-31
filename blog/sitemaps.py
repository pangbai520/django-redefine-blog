from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from .models import ArticleModel, SiteConfiguration


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
        site = SiteConfiguration.get_config()
        pages = ["index", "archives", "categories", "tags"]
        if site.friends_enabled:
            pages.append("friends")
        if site.bookmarks_enabled:
            pages.append("bookmarks")
        if site.essays_enabled:
            pages.append("essays")
        if site.masonry_enabled:
            pages.append("masonry")
        return pages

    def location(self, name):
        return reverse(name)
