from urllib.parse import unquote
from django.shortcuts import render, get_object_or_404
from django.http import Http404, HttpResponse, JsonResponse
from django.urls import reverse
from django.core.paginator import Paginator
from django.db.models import Count, F, Q
from .models import (
    ArticleModel,
    BookmarkCategory,
    Category,
    Essay,
    FriendCategory,
    MasonryImage,
    SiteConfiguration,
    StandalonePage,
    Tag,
    TrafficModel,
)
from core.markdown.extensions import get_extensions
from markdown import Markdown
from django.utils.safestring import mark_safe
from django.utils import timezone
from django.utils.translation import gettext as _
import re

from .cache_utils import versioned_cache_page
from .middleware import record_request_traffic
from .recommendations import related_articles
from .search import search_articles


def _render_page_markdown(page, site):
    content = page.localized_content()
    if not content:
        return ""
    markdown = Markdown(extensions=get_extensions(site))
    return mark_safe(markdown.convert(content))


def _standalone_page(site, page_type, default_title):
    page = (
        StandalonePage.objects.filter(config=site, page_type=page_type)
        .prefetch_related("translations")
        .first()
    )
    if page is None:
        defaults = StandalonePage.BUILTIN_DEFAULTS[page_type]
        legacy_field = {
            StandalonePage.FRIENDS: "friends_enabled",
            StandalonePage.BOOKMARKS: "bookmarks_enabled",
            StandalonePage.ESSAYS: "essays_enabled",
            StandalonePage.MASONRY: "masonry_enabled",
        }.get(page_type)
        enabled = getattr(site, legacy_field, defaults["enabled"]) if legacy_field else defaults["enabled"]
        page = StandalonePage(
            config=site,
            page_type=page_type,
            title=default_title,
            slug=defaults["slug"],
            enabled=enabled,
            friends_columns=getattr(site, "friends_page_columns", 2),
            tags_style=getattr(site, "tags_page_style", "blur"),
        )
    if not page.enabled:
        raise Http404
    page.rendered_content = _render_page_markdown(page, site)
    page.rendered_title = page.localized_title()
    return page


def page_not_found(request, exception):
    """Render Redefine's 404 page instead of Django's generic response."""
    return render(request, "404.html", {
        "page_title": _("Page Not Found"),
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
    # Record before rendering so the first real visit is visible immediately.
    # The middleware sees the same cache key afterwards and does not double count.
    recorded = record_request_traffic(
        request,
        # An explicit article view is already constrained to a published HTML
        # page. Requiring Sec-Fetch headers here drops legitimate mobile and
        # privacy-browser reads; bot and hourly IP/path checks still apply.
        require_browser_navigation=False,
    )
    if recorded:
        ArticleModel.objects.filter(pk=article.pk).update(
            view_count=F("view_count") + 1
        )
        article.view_count += 1
    article_pv = article.view_count
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


def robots_txt(request):
    """Advertise public content while keeping account and API routes out of indexes."""
    sitemap_url = request.build_absolute_uri(
        reverse("django.contrib.sitemaps.views.sitemap")
    )
    body = "\n".join((
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin/",
        "Disallow: /api/",
        "Disallow: /comments/",
        "Disallow: /mdeditor/",
        f"Sitemap: {sitemap_url}",
        "",
    ))
    return HttpResponse(body, content_type="text/plain; charset=utf-8")

@versioned_cache_page("content", timeout=10 * 60)
def archives(request):
    # order archives strictly by date, because home-page sticky ordering can
    # otherwise split one year into several sections
    articles_qs = ArticleModel.objects.published().order_by('-created_at', 'title')

    site = SiteConfiguration.get_config()
    standalone_page = _standalone_page(site, StandalonePage.ARCHIVES, _("Archives"))
    context = {
        # render the complete archive on one page, matching Hexo's archive helper
        "page_title": standalone_page.rendered_title,
        "standalone_page": standalone_page,
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
    site = SiteConfiguration.get_config()
    standalone_page = _standalone_page(site, StandalonePage.CATEGORIES, _("Categories"))
    context = {
        "is_homepage": False,
        "is_paginated": False,
        "has_header": True,
        "page_title": standalone_page.rendered_title,
        "standalone_page": standalone_page,
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
    site = SiteConfiguration.get_config()
    standalone_page = _standalone_page(site, StandalonePage.TAGS, _("Tags"))
    tags = list(
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

    # Hexo's tagcloud helper caps cloud mode at 100 entries.  The blur list
    # deliberately remains complete.
    if standalone_page.tags_style == "cloud":
        tags = tags[:100]

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
        "page_title": standalone_page.rendered_title,
        "standalone_page": standalone_page,
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
    standalone_page = _standalone_page(site, StandalonePage.BOOKMARKS, _("Bookmarks"))

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
        "page_title": standalone_page.rendered_title,
        "standalone_page": standalone_page,
        "categories": categories,
        "is_homepage": False,
        "has_header": True,
    })


def essays(request):
    site = SiteConfiguration.get_config()
    standalone_page = _standalone_page(site, StandalonePage.ESSAYS, _("Essays"))

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
        "page_title": standalone_page.rendered_title,
        "standalone_page": standalone_page,
        "essays": entries,
        "is_homepage": False,
        "has_header": True,
    })


def masonry(request):
    site = SiteConfiguration.get_config()
    standalone_page = _standalone_page(site, StandalonePage.MASONRY, _("Masonry"))

    images = MasonryImage.objects.filter(config=site)
    return render(request, "pages/masonry/masonry.html", {
        "page_title": standalone_page.rendered_title,
        "standalone_page": standalone_page,
        "images": images,
        "is_homepage": False,
        "has_header": True,
    })


def friends(request):
    site = SiteConfiguration.get_config()
    standalone_page = _standalone_page(site, StandalonePage.FRIENDS, _("Friends"))
    categories = FriendCategory.objects.prefetch_related("links")
    return render(request, "pages/friends/friends.html", {
        "page_title": standalone_page.rendered_title,
        "standalone_page": standalone_page,
        "categories": categories,
        "is_homepage": False,
        "has_header": True,
    })


def standalone_page(request, slug):
    site = SiteConfiguration.get_config()
    page = get_object_or_404(
        StandalonePage.objects.prefetch_related("translations"),
        config=site,
        page_type=StandalonePage.CUSTOM,
        slug=slug,
        enabled=True,
    )
    page.rendered_title = page.localized_title()
    page.rendered_content = _render_page_markdown(page, site)
    return render(request, "pages/standalone/page.html", {
        "page_title": page.rendered_title,
        "standalone_page": page,
        "is_homepage": False,
        "has_header": True,
    })
