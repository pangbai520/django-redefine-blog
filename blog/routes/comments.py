from django.urls import path

from blog import account_views, comment_views as views

urlpatterns = [
    path(
        "api/comments/login/",
        account_views.login_ajax,
        name="comment_login_ajax",
    ),
    path(
        "api/comments/register/",
        account_views.register_ajax,
        name="comment_register_ajax",
    ),
    path("api/comments/upload/", views.comment_upload, name="comment_upload"),
    path("api/comments/preview/", views.comment_preview, name="comment_preview"),
    path(
        "api/comments/gitalk/oauth/",
        views.gitalk_oauth,
        name="gitalk_oauth_proxy",
    ),
    path("api/comments/<str:slug>/", views.comments, name="comment_list"),
    path(
        "api/comments/<str:slug>/create/",
        views.create_comment,
        name="comment_create",
    ),
    path(
        "api/page-comments/<str:slug>/",
        views.page_comments,
        name="page_comment_list",
    ),
    path(
        "api/page-comments/<str:slug>/create/",
        views.create_page_comment,
        name="page_comment_create",
    ),
    path(
        "api/comments/<int:comment_id>/like/",
        views.toggle_like,
        name="comment_like",
    ),
    path(
        "api/comments/<int:comment_id>/edit/",
        views.edit_comment,
        name="comment_edit",
    ),
    path(
        "api/comments/<int:comment_id>/delete/",
        views.delete_comment,
        name="comment_delete",
    ),
    path(
        "api/comments/<int:comment_id>/sticky/",
        views.toggle_sticky,
        name="comment_sticky",
    ),
    path(
        "api/comment-notifications/",
        views.notifications,
        name="comment_notifications",
    ),
    path(
        "api/comment-notifications/read/",
        views.mark_notifications_read,
        name="comment_notifications_read",
    ),
    path("api/comment-assets/", views.comment_assets, name="comment_assets"),
    path("api/comment-gif-proxy/", views.comment_gif_proxy, name="comment_gif_proxy"),
]
