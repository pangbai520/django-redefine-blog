from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap
from . import views
from .ops_views import health
from .feeds import LatestArticlesFeed
from .sitemaps import ArticleSitemap, StaticPageSitemap
from .cache_utils import versioned_cache_page

sitemaps = {
    "articles": ArticleSitemap,
    "static": StaticPageSitemap,
}

urlpatterns = [
    path("health/", health, name="health"),
    path("robots.txt", views.robots_txt, name="robots_txt"),
    path("", views.index, name="index"),
    path("search.json", views.search_data, name="search_data"),
    path(
        "feed.xml",
        versioned_cache_page("content", 60 * 60)(LatestArticlesFeed()),
        name="article_feed",
    ),
    path(
        "sitemap.xml",
        versioned_cache_page("content", 60 * 60)(sitemap),
        {"sitemaps": sitemaps},
        name="django.contrib.sitemaps.views.sitemap",
    ),
    path("article/<str:slug>/", views.article, name="article"),
    path("archives/", views.archives, name="archives"),
    path("categories/", views.categories, name="categories"),
    path(
        "categories/<str:slug>/",
        views.categories_detail,
        name="categories_detail",
    ),
    path("tags/", views.tags, name="tags"),
    path("tags/<str:slug>/", views.tags_detail, name="tags_detail"),
    path("bookmarks/", views.bookmarks, name="bookmarks"),
    path("essays/", views.essays, name="essays"),
    path("masonry/", views.masonry, name="masonry"),
    path("friends/", views.friends, name="friends"),
    path("", include("blog.routes.accounts")),
    path("", include("blog.routes.comments")),
    # Keep this last: fixed application routes take precedence over custom pages.
    path("<str:slug>/", views.standalone_page, name="standalone_page"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
