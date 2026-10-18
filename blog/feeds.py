from django.contrib.syndication.views import Feed
from django.urls import reverse
from django.utils.html import strip_tags

from .models import ArticleModel, SiteConfiguration


class LatestArticlesFeed(Feed):
    """Publish the same visible article set used by the public site."""

    def title(self):
        return SiteConfiguration.get_config().site_name

    def link(self):
        return reverse("index")

    def description(self):
        site = SiteConfiguration.get_config()
        return site.site_description or site.site_subname or site.site_name

    def items(self):
        return ArticleModel.objects.published().order_by("-created_at")[:20]

    def item_title(self, item):
        return item.title

    def item_description(self, item):
        return strip_tags(item.auto_excerpt)

    def item_pubdate(self, item):
        return item.created_at

    def item_updateddate(self, item):
        return item.updated_at

    def item_author_name(self, item):
        return item.writer or SiteConfiguration.get_config().site_author
