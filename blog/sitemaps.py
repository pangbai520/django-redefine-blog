from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from .models import ArticleModel, SiteConfiguration, StandalonePage


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
        return [None, *StandalonePage.objects.filter(
            config=site,
            enabled=True,
            include_in_sitemap=True,
        ).order_by("page_type", "slug")]

    def location(self, page):
        return reverse("index") if page is None else page.get_absolute_url()

    def lastmod(self, page):
        return None if page is None else page.updated_at
