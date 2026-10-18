from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap
from . import views
from . import comment_views
from .feeds import LatestArticlesFeed
from .sitemaps import ArticleSitemap, StaticPageSitemap


sitemaps = {
    "articles": ArticleSitemap,
    "static": StaticPageSitemap,
}

urlpatterns = [
    path("", views.index, name="index"),
    path("search.json", views.search_data, name="search_data"),
    path("feed.xml", LatestArticlesFeed(), name="article_feed"),
    path("sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="django.contrib.sitemaps.views.sitemap"),
    path('article/<str:slug>/', views.article, name='article'),
    path('archives/', views.archives, name='archives'),
    path('categories/', views.categories, name='categories'),
    path('categories/<str:slug>/', views.categories_detail, name='categories_detail'),
    path('tags/', views.tags, name='tags'),
    path('tags/<str:slug>/', views.tags_detail, name='tags_detail'),
    path('bookmarks/', views.bookmarks, name='bookmarks'),
    path('essays/', views.essays, name='essays'),
    path('masonry/', views.masonry, name='masonry'),
    path('friends/', views.friends, name='friends'),
    path('comments/register/', comment_views.register, name='comment_register'),
    path('comments/login/', comment_views.login_view, name='comment_login'),
    path('api/comments/login/', comment_views.login_ajax, name='comment_login_ajax'),
    path('api/comments/register/', comment_views.register_ajax, name='comment_register_ajax'),
    path('comments/logout/', comment_views.logout_view, name='comment_logout'),
    path('comments/verify/<uidb64>/<token>/', comment_views.verify, name='comment_verify'),
    path('api/comments/upload/', comment_views.comment_upload, name='comment_upload'),
    path('api/comments/preview/', comment_views.comment_preview, name='comment_preview'),
    path('api/comments/<str:slug>/', comment_views.comments, name='comment_list'),
    path('api/comments/<str:slug>/create/', comment_views.create_comment, name='comment_create'),
    path('api/comments/<int:comment_id>/like/', comment_views.toggle_like, name='comment_like'),
    path('api/comments/<int:comment_id>/edit/', comment_views.edit_comment, name='comment_edit'),
    path('api/comments/<int:comment_id>/delete/', comment_views.delete_comment, name='comment_delete'),
    path('api/comments/<int:comment_id>/sticky/', comment_views.toggle_sticky, name='comment_sticky'),
    path('api/comment-notifications/', comment_views.notifications, name='comment_notifications'),
    path('api/comment-notifications/read/', comment_views.mark_notifications_read, name='comment_notifications_read'),
    path('api/comment-assets/', comment_views.comment_assets, name='comment_assets'),
    path('api/comment-gif-proxy/', comment_views.comment_gif_proxy, name='comment_gif_proxy'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
