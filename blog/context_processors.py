from django.core.cache import cache
from django.db import models
from django.conf import settings
from django.utils import timezone, translation
from django.db.models import Count, Q
from django.urls import reverse
from .cache_utils import published_cache_timeout
from .models import (
    ArticleModel,
    Category,
    SiteConfiguration,
    StandalonePage,
    Tag,
    TrafficModel,
    UserProfile,
)


CACHE_KEY = "actived_site_config"
CACHE_TIMEOUT = 60 * 60 * 24


def site_processor(request):
    current_lang = translation.get_language()
    lang_map = {
        'zh-hans': 'zh-CN',
        'zh-hant': 'zh-TW',
        'zh-hk': 'zh-HK',
        'zh-tw': 'zh-TW',
        'en-us': 'en',
    }
    language_options = []
    language_badges = getattr(settings, "LANGUAGE_SWITCHER_BADGES", {})
    for code, name in settings.LANGUAGES:
        badge = language_badges.get(code, "🌐")
        language_options.append(
            {"code": code, "name": name, "badge": badge, "badge_kind": "emoji"}
        )
    return {
        "SITE_LANG": lang_map.get(current_lang, current_lang),
        "LANGUAGE_SWITCHER_OPTIONS": language_options,
        "PROJECT_VERSION": getattr(settings, "PROJECT_VERSION", ""),
        "github_oauth_url": (
            reverse("github_login")
            if getattr(settings, "GITHUB_OAUTH_ENABLED", False)
            else ""
        ),
        # keep structural constants project-owned, so changing the active site
        # configuration cannot unexpectedly reflow the deployed theme
        "SITE_CONTENT_MAXWIDTH": getattr(settings, "SITE_CONTENT_MAXWIDTH", 1000),
        "SITE_SIDEBAR_WIDTH": getattr(settings, "SITE_SIDEBAR_WIDTH", 210),
        "NAVBAR_WIDTH": getattr(
            settings, "NAVBAR_WIDTH", {"home": 1200, "pages": 1000}
        ),
        "ARTICLE_FONT_SIZE": getattr(settings, "ARTICLE_FONT_SIZE", 16),
        "ARTICLE_LINE_HEIGHT": getattr(settings, "ARTICLE_LINE_HEIGHT", 1.5),
        "ARTICLE_IMG_BORDER_RADIUS": getattr(
            settings, "ARTICLE_IMG_BORDER_RADIUS", 14
        ),
        "ARTICLE_HEADINGS_TOP_SPACING": getattr(
            settings,
            "ARTICLE_HEADINGS_TOP_SPACING",
            {
                "h1": "3.2rem",
                "h2": "2.4rem",
                "h3": "1.9rem",
                "h4": "1.6rem",
                "h5": "1.4rem",
                "h6": "1.3rem",
            },
        ),
    }


def site_configuration_processor(request):
    """
    A context processor to add the active SiteConfiguration to the template context.
    """
    site = cache.get(CACHE_KEY)
    if not site:
        site = SiteConfiguration.load()
        cache.set(CACHE_KEY, site, CACHE_TIMEOUT)

    WORD_COUNT_KEY = "total_word_count"
    total_words = cache.get(WORD_COUNT_KEY)
    if total_words is None:
        result = ArticleModel.objects.published().aggregate(
            total=models.Sum('word_counter')
        )
        total_words = result['total'] or 0
        cache.set(
            WORD_COUNT_KEY,
            total_words,
            published_cache_timeout(CACHE_TIMEOUT),
        )

    required_comment_keys = {
        "waline": ("serverUrl",),
        "gitalk": ("clientID", "clientSecret", "owner", "repo"),
        "twikoo": ("server_url",),
        "giscus": ("repo", "repo_id", "category_id"),
        "internal": (),
    }
    comment_config = site.comment_options
    required_keys = required_comment_keys.get(site.comment_system, ())
    owner_profile = (
        UserProfile.objects.filter(user__is_superuser=True, user__is_active=True)
        .select_related("user")
        .order_by("user__date_joined", "user_id")
        .first()
    )
    blog_author_name = site.site_author
    blog_author_avatar = None
    if owner_profile:
        blog_author_name = owner_profile.display_name.strip() or site.site_author
        blog_author_avatar = owner_profile.avatar or None

    standalone_cache_key = f"standalone-page-types:{site.pk}"
    enabled_standalone_pages = cache.get(standalone_cache_key)
    if enabled_standalone_pages is None:
        enabled_standalone_pages = tuple(
            StandalonePage.objects.filter(config=site, enabled=True).values_list(
                "page_type", flat=True
            )
        )
        cache.set(standalone_cache_key, enabled_standalone_pages, None)

    return {
        'site': site,
        'enabled_standalone_pages': set(enabled_standalone_pages),
        'blog_author_name': blog_author_name,
        'blog_author_avatar': blog_author_avatar,
        'total_words': total_words,
        'comment_system_configured': bool(
            site.comment_enabled
            and (
                site.comment_system == "internal"
                or (required_keys and all(comment_config.get(key) for key in required_keys))
            )
        ),
    }




def site_stats_processor(request):
    _CACHE_TIMEOUT = 10 * 60  # Ten minutes.
    data = cache.get_many(["site_stats_counts", "site_traffic"])
    stats = data.get("site_stats_counts")

    if stats is None:
        now = timezone.now()
        public_articles = Q(
            articlemodel__is_published=True,
            articlemodel__created_at__lte=now,
        )
        articles_count = ArticleModel.objects.published().count()
        tags_count = Tag.objects.annotate(
            post_count=Count('articlemodel', filter=public_articles)
        ).filter(post_count__gt=0).count()
        categories_count = Category.objects.annotate(
            post_count=Count('articlemodel', filter=public_articles)
        ).filter(post_count__gt=0).count()

        stats = {
            'articles_count': articles_count,
            'tags_count': tags_count,
            'categories_count': categories_count,
        }
        cache.set(
            "site_stats_counts",
            stats,
            published_cache_timeout(_CACHE_TIMEOUT),
        )

    traffic = data.get("site_traffic")

    if traffic is None:
        site_pv = TrafficModel.objects.count()
        site_uv = TrafficModel.objects.values('ip').distinct().count()
        traffic = {
            'site_pv': site_pv,
            'site_uv': site_uv,
        }
        cache.set("site_traffic", traffic, _CACHE_TIMEOUT)


    return {
        **stats,
        **traffic,
    }
