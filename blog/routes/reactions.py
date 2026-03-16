from django.urls import path

from blog import reaction_views


urlpatterns = [
    path(
        "api/article-reactions/<str:slug>/",
        reaction_views.article_reactions,
        name="article_reactions",
    ),
]
