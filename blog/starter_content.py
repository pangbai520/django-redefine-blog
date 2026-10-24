from datetime import datetime, timezone as datetime_timezone

from django.db import transaction
from django.utils import timezone as django_timezone

from .models import (
    ArticleModel,
    Category,
    CommentBadge,
    CommentEmojiPack,
    MenuLink,
    SiteConfiguration,
    Tag,
)


SITE_DEFAULTS = {
    "site_name": "Django Redefine",
    "site_subname": "Redefine Your Django Journey.",
    "site_author": "The Redefine Team",
    "site_keywords": "Redefine,Django",
    "site_description": "A Django blog based on Redefine.",
    "site_avatar": "",
    "site_logo": "",
    "preloader_message": "",
    "hb_title": "Django Redefine",
    "og_description": "Django Redefine, Redefine Your Django Journey.",
    "subtitle_enabled": True,
    "subtitle_text": ["A simple, fast and pure theme.", "Redefine your writing."],
    "hb_light_text": "#ffffff",
    "social_links_enabled": True,
    "sidebar_announcement": "Redefine your writing.",
    "comment_require_login": True,
    "comment_email_notifications": False,
    "comment_allow_guest": False,
    "comment_config": {"internal": {}},
    "article_dateformat": "YYYY-MM-DD HH:mm:ss",
    "show_word_counter": False,
    "codeblock_dark": "github-dark",
    "footer_sitestart": datetime(2022, 8, 17, 3, 45, tzinfo=datetime_timezone.utc),
    "friends_page_columns": 3,
}

MENU_DEFAULTS = (
    {"link_location": "sidebar", "name": "Archives", "url": "/archives", "icon": "fa-regular fa-archive", "order": 1},
    {"link_location": "sidebar", "name": "Tags", "url": "/tags", "icon": "fa-regular fa-tags", "order": 2},
    {"link_location": "sidebar", "name": "Categories", "url": "/categories", "icon": "fa-regular fa-folder", "order": 3},
    {"link_location": "navbar", "name": "Home", "url": "/", "icon": "fa-regular fa-house", "order": 4},
    {"link_location": "navbar", "name": "Archives", "url": "/archives", "icon": "fa-regular fa-archive", "order": 5},
    {"link_location": "navbar", "name": "More", "url": "#", "icon": "fa-regular fa-link", "order": 12},
    {"link_location": "navbar", "name": "Redefine", "url": "https://redefine.ohevan.com/", "order": 13, "parent": "More"},
    {"link_location": "social", "name": "Github", "url": "https://github.com", "order": 16},
)

HELLO_WORLD_CONTENT = """Welcome to [Django](https://www.djangoproject.com/)! This is your very first post. Check [documentation](https://docs.djangoproject.com/) for more info. If you get any problems when using Django, you may find the answer in [Stack Overflow](https://stackoverflow.com/questions/tagged/django) or you can ask on [GitHub](https://github.com/django/django/issues).

## Quick Start

### Create a new project

```text
$ django-admin startproject mysite
```

More info: [Getting Started](https://docs.djangoproject.com/en/stable/intro/tutorial01/)

### Run server

```bash
$ cd mysite
$ python manage.py runserver
```

More info: [Runserver](https://docs.djangoproject.com/en/stable/ref/django-admin/#runserver)

### Create a new app

```bash
$ python manage.py startapp myapp
```

More info: [Apps](https://docs.djangoproject.com/en/stable/ref/applications/)

### Generate static files

```bash
$ python manage.py collectstatic
```

More info: [Static files](https://docs.djangoproject.com/en/stable/howto/static-files/)

### Deploy to remote sites

Deployment varies by platform. See Django's [deployment checklist](https://docs.djangoproject.com/en/stable/howto/deployment/checklist/) before publishing the site.
"""


@transaction.atomic
def install_starter_content(update_existing=False):
    """Install a useful public starting point without importing owner data."""
    site = SiteConfiguration.objects.filter(is_active=True).first()
    if site is None:
        site = SiteConfiguration.objects.first()
    if site is not None and not update_existing:
        return False

    if site is None:
        site = SiteConfiguration.objects.create(
            config_name="Default Config",
            is_active=True,
            **SITE_DEFAULTS,
        )
    else:
        for field, value in SITE_DEFAULTS.items():
            setattr(site, field, value)
        site.is_active = True
        site.save()

    parents = {}
    for item in MENU_DEFAULTS:
        values = dict(item)
        parent_name = values.pop("parent", None)
        parent = parents.get(parent_name)
        link, _ = MenuLink.objects.update_or_create(
            config=site,
            link_location=values["link_location"],
            name=values["name"],
            parent=parent,
            defaults=values,
        )
        parents[link.name] = link

    Category.objects.get_or_create(name="Category", defaults={"slug": "category"})
    Tag.objects.get_or_create(name="Tag", defaults={"slug": "tag"})
    if not ArticleModel.objects.exists():
        ArticleModel.objects.create(
            title="Hello World",
            slug="hello-world",
            content=HELLO_WORLD_CONTENT,
            is_published=True,
            created_at=django_timezone.make_aware(
                datetime(1900, 1, 1, 0, 0),
                django_timezone.get_default_timezone(),
            ),
        )

    CommentBadge.objects.update_or_create(
        config=site,
        name="博主",
        defaults={"color": "", "admin_only": True, "enabled": True, "order": 0},
    )
    CommentEmojiPack.objects.update_or_create(
        config=site,
        name="bilibili",
        defaults={
            "base_url": "https://unpkg.com/@waline/emojis@1.2.0/bmoji",
            "enabled": True,
            "order": 0,
        },
    )
    CommentEmojiPack.objects.filter(config=site, name__iexact="tieba").delete()
    return True
