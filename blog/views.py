from urllib.parse import unquote
from django.shortcuts import render, get_object_or_404
from django.http import Http404, JsonResponse
from django.urls import reverse
from django.core.paginator import Paginator
from django.db.models import Count, Q
from .models import (
    ArticleModel,
    BookmarkCategory,
    Category,
    Essay,
    FriendCategory,
    MasonryImage,
    SiteConfiguration,
    Tag,
    TrafficModel,
)
from core.markdown.extensions import get_extensions
from markdown import Markdown
from django.utils.safestring import mark_safe
from django.utils import timezone
import re

from .cache_utils import versioned_cache_page
from .recommendations import related_articles
from .search import search_articles


def page_not_found(request, exception):
    """Render Redefine's 404 page instead of Django's generic response."""
    return render(request, "404.html", {
        "page_title": "Page Not Found",
        "is_homepage": False,
        "has_header": True,
    }, status=404)


def _recommend_articles(article, site):
    """Return the cached, database-ranked related article set."""
    if not site.recommendation_enabled:
        return []
    limit = max(int(site.recommendation_limit or 0), 0)
    if limit == 0:
        return []
    path = article.get_absolute_url()
    for prefix in (site.recommendation_skip_dirs or []):
        if path.lstrip('/').startswith(str(prefix).lstrip('/')):
            return []

    return related_articles(article, limit)


def index(request):
    articles_qs = ArticleModel.objects.published()
    paginator = Paginator(articles_qs, 10)
    page_number = request.GET.get('page')
    articles_page = paginator.get_page(page_number)

    context = {
        'articles_page': articles_page,
        'is_homepage': True,
    }
    return render(request, 'pages/home/index.html', context)


def search_data(request):
    """Return a bounded server-side search result instead of the whole corpus."""
    query = request.GET.get("q", "")
    results, backend = search_articles(query)
    response = JsonResponse({
        "query": query[:100],
        "results": results,
        "backend": backend,
    })
    response["Cache-Control"] = "public, max-age=60"
    return response


def article(request, slug):
    article = get_object_or_404(ArticleModel.objects.published(), slug=slug)
    site = SiteConfiguration.get_config()
    article_path = reverse('article', args=[article.slug])
    article_pv = (TrafficModel.objects.filter(path=article_path).count())
    post_count = ArticleModel.objects.published().count()
    prev_article = (
        ArticleModel.objects.published()
        .filter(
            Q(created_at__lt=article.created_at)
            | Q(created_at=article.created_at, pk__lt=article.pk)
        )
        .order_by('-created_at', '-pk')
        .first()
    )
    next_article = (
        ArticleModel.objects.published()
        .filter(
            Q(created_at__gt=article.created_at)
            | Q(created_at=article.created_at, pk__gt=article.pk)
        )
        .order_by('created_at', 'pk')
        .first()
    )
    full_url = unquote(request.build_absolute_uri(article.get_absolute_url()))

    recommendations = _recommend_articles(article, site)
    context = {
        "page_title": article.title,
        "article": article,
        "article_pv": article_pv,
        "post_count": post_count,
        "prev_article": prev_article,
        "next_article": next_article,
        "full_url": full_url,
        "recommendations": recommendations,
        "recommendations_mobile": recommendations[: max(int(site.recommendation_mobile_limit or 0), 0)],
        "is_homepage": False,
        "is_postpage": True,
    }
    return render(request, "pages/post/article.html", context)

@versioned_cache_page("content", timeout=10 * 60)
def archives(request):
    # order archives strictly by date, because home-page sticky ordering can
    # otherwise split one year into several sections
    articles_qs = ArticleModel.objects.published().order_by('-created_at', 'title')

    context = {
        # render the complete archive on one page, matching Hexo's archive helper
        "page_title": "Archives",
        "articles_page": articles_qs,
        "is_homepage": False,
        "has_header": True,
    }
    return render(request, "pages/archive/archives.html", context)

@versioned_cache_page("content", timeout=10 * 60)
def categories(request):
    now = timezone.now()
    categories = list(
        Category.objects
        .annotate(
            article_count=Count(
                'articlemodel',
                filter=Q(
                    articlemodel__is_published=True,
                    articlemodel__created_at__lte=now,
                )
            )
        )
        .order_by("parent_id", "name")
    )
    by_parent = {}
    for category in categories:
        category.children_list = []
        by_parent.setdefault(category.parent_id, []).append(category)

    def build_tree(category):
        children = []
        for child in by_parent.get(category.pk, []):
            visible_child = build_tree(child)
            if visible_child is not None:
                children.append(visible_child)
        category.children_list = children
        category.tree_article_count = category.article_count + sum(
            child.tree_article_count for child in children
        )
        return category if category.tree_article_count else None

    category_tree = []
    for root in by_parent.get(None, []):
        visible_root = build_tree(root)
        if visible_root is not None:
            category_tree.append(visible_root)
    context = {
        "is_homepage": False,
        "is_paginated": False,
        "has_header": True,
        "page_title": "Categories",
        'categories': categories,
        'category_tree': category_tree,
    }
    return render(request, "pages/category/categories.html", context)

@versioned_cache_page("content", timeout=10 * 60)
def categories_detail(request, slug):
    category = get_object_or_404(Category, slug=slug)
    articles_qs = (
        ArticleModel.objects.published()
        .filter(category=category)
        .order_by('-created_at', 'title')
    )
    paginator = Paginator(articles_qs, 10)
    page_number = request.GET.get('page')
    articles_page = paginator.get_page(page_number)


    context = {
        "page_title": category.name,
        "page": category,
        "articles_page": articles_page,
        "is_homepage": False,
        "is_paginated": articles_page.has_other_pages(),
        "has_header": True,
    }
    return render(request, "pages/category/categories_detail.html", context)

@versioned_cache_page("content", timeout=10 * 60)
def tags(request):
    now = timezone.now()
    tags = (
        Tag.objects
        .annotate(
            post_count=Count(
                'articlemodel',
                filter=Q(
                    articlemodel__is_published=True,
                    articlemodel__created_at__lte=now,
                ),
            )
        )
        .filter(post_count__gt=0)
        .order_by('-post_count', 'name')
    )

    if tags:
        # normalize tag counts first, so the smallest and largest cloud labels stay bounded
        counts = [t.post_count for t in tags]
        max_c = max(counts)
        min_c = min(counts)

        diff = max_c - min_c
        for tag in tags:
            if diff > 0:
                # interpolate between 1rem and 5rem, so frequency remains visible without extremes
                tag.weight = round(1 + (tag.post_count - min_c) / diff * 4, 2)
            else:
                tag.weight = 2

    context = {
        "tags": tags,
        "page_title": "Tags",
        "is_paginated": False,
        "has_header": True,
    }
    return render(request, 'pages/tag/tags.html', context)

@versioned_cache_page("content", timeout=10 * 60)
def tags_detail(request, slug):
    tag = get_object_or_404(Tag, slug=slug)
    articles_qs = (
        ArticleModel.objects.published()
        .filter(tags=tag)
        .order_by('-created_at', 'title')
    )
    paginator = Paginator(articles_qs, 10)
    page_number = request.GET.get('page')
    articles_page = paginator.get_page(page_number)


    context = {
        "page_title": tag.name,
        "tag": tag,
        "articles_page": articles_page,
        "is_homepage": False,
        "is_paginated": articles_page.has_other_pages(),
        # let the custom block own the heading, so page_base does not render a duplicate h1
        "has_header": True,
    }

    return render(request, "pages/tag/tags_detail.html", context)


def bookmarks(request):
    site = SiteConfiguration.get_config()
    if not site.bookmarks_enabled:
        raise Http404

    categories = list(
        BookmarkCategory.objects.filter(config=site).prefetch_related("items")
    )
    # follow Hexo's lowercase anchor convention while preserving non-Latin
    # names and disambiguating duplicate bookmark categories
    used_anchors = set()
    for category in categories:
        base = re.sub(r"\s+", "-", category.name.strip().lower()) or "category"
        anchor = base
        suffix = 2
        while anchor in used_anchors:
            anchor = f"{base}-{suffix}"
            suffix += 1
        used_anchors.add(anchor)
        category.anchor_id = anchor
    return render(request, "pages/bookmarks/bookmarks.html", {
        "page_title": "Bookmarks",
        "categories": categories,
        "is_homepage": False,
        "has_header": True,
    })


def essays(request):
    site = SiteConfiguration.get_config()
    if not site.essays_enabled:
        raise Http404

    markdown = Markdown(extensions=get_extensions(site))
    entries = []
    for essay in Essay.objects.filter(config=site, published=True):
        # reset per entry, so headings and extension state cannot leak from one
        # essay into the next item on the timeline
        html = markdown.reset().convert(essay.content)
        entries.append({
            "essay": essay,
            "html": mark_safe(html),
        })

    return render(request, "pages/essays/essays.html", {
        "page_title": "Essays",
        "essays": entries,
        "is_homepage": False,
        "has_header": True,
    })


def masonry(request):
    site = SiteConfiguration.get_config()
    if not site.masonry_enabled:
        raise Http404

    images = MasonryImage.objects.filter(config=site)
    return render(request, "pages/masonry/masonry.html", {
        "page_title": "Masonry",
        "images": images,
        "is_homepage": False,
        "has_header": True,
    })


def friends(request):
    categories = FriendCategory.objects.prefetch_related("links")
    return render(request, "pages/friends/friends.html", {
        "page_title": "Friends",
        "categories": categories,
        "is_homepage": False,
        "has_header": True,
    })
