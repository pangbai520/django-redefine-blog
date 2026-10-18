<div align="right">
  <img src="https://img.shields.io/badge/-English-A31F34?style=for-the-badge" alt="English">
  <a href="README_zh-CN.md"><img src="https://img.shields.io/badge/-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-545759?style=for-the-badge" alt="简体中文"></a>
  <a href="README_zh-TW.md"><img src="https://img.shields.io/badge/-%E7%B9%81%E9%AB%94%E4%B8%AD%E6%96%87-545759?style=for-the-badge" alt="繁體中文"></a>
</div>

<p align="center">
  <img width="92" src="blog/static/images/redefine-logo.webp" alt="Redefine logo">
</p>

<h1 align="center">django-redefine-blog</h1>

<p align="center">
  A Redefine-style blog rewritten with Django
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12%E2%80%933.14-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.12 to 3.14">
  <img src="https://img.shields.io/badge/Django-6.0-0C4B33?style=flat-square&logo=django&logoColor=white" alt="Django 6.0">
  <img src="https://img.shields.io/badge/license-GPL--3.0-A31F34?style=flat-square" alt="GPL-3.0">
</p>

This project is a port of [hexo-theme-redefine](https://github.com/EvanNotFound/hexo-theme-redefine) 2.8.5.
Its templates, page layouts, and Markdown components have been moved to Django, with database-backed content management, comments, search, and other blog features added on top.

## Features

- Redefine-style home, article, archive, category, tag, and standalone pages with responsive layouts
- light and dark modes, Swup page transitions, local search, table of contents, image viewer, and side tools
- Friends, Bookmarks, Essays, and Masonry pages managed through Django Admin
- compatibility with the commonly used Note, Folding, Tabs, Buttons, and code block syntax from Redefine 2.8.5
- drafts, scheduled publishing, stable links, recommended articles, RSS, and Sitemap
- a built-in comment system with accounts, moderation, badges, likes, replies, emoji, GIFs, and image uploads
- optional Waline, Gitalk, Twikoo, and Giscus integrations
- `export_blog` and `import_blog` commands for moving articles, accounts, settings, and uploaded files

## Running locally

Python 3.12 ~ Python 3.14 are supported.

```bash
python -m venv .venv
```

Activate the virtual environment:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# Linux and macOS
source .venv/bin/activate
```

Install the dependencies and initialize the database:

```bash
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open `http://127.0.0.1:8000/admin/` and sign in with the superuser you just created. The first migration creates a default site configuration; site information, navigation, comments, and theme options can then be changed in the admin.

The development setup uses SQLite and prints email to the terminal. Production secrets, domains, and mail settings are read from environment variables. Read [.env.example](.env.example) and [DEPLOYMENT.md](DEPLOYMENT.md) before deployment.

## Tests

The Django tests cover publishing rules, comments, Markdown, the admin, RSS, backups, and data constraints. The frontend tests run the browser modules directly.

```bash
python manage.py check
python manage.py test blog
python manage.py makemigrations --check --dry-run
node --test tests/frontend-regressions.cjs
```

Node.js is only used for frontend tests. Running the site does not require a frontend build.

## Content and backups

Uploaded files are stored in `blog/resources/`, which is ignored by Git. To move a blog to another installation, use the built-in archive commands instead of committing the database and media files:

```bash
python manage.py export_blog blog-backup.zip
python manage.py import_blog blog-backup.zip
```

An archive may contain password hashes, private settings, and uploaded files. Store it as sensitive data. Import and replacement options are documented in [DEPLOYMENT.md](DEPLOYMENT.md).

## Notes

- Site settings are managed in Django Admin. Layout constants that affect the project structure remain in `config/settings.py`.
- Site PV, Site UV, and article PV already have data support. Separate visibility switches for the three counters will be added later.

See [ADMIN_GUIDE.md](ADMIN_GUIDE.md) for notes on the administration interface.

## Credits and license

The frontend is based on [hexo-theme-redefine](https://github.com/EvanNotFound/hexo-theme-redefine), created by [EvanNotFound](https://github.com/EvanNotFound). Redefine uses GPL-3.0, and this project follows the same license.

Third-party libraries and fonts included in the repository remain subject to their own copyright and license terms. Read [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) before redistributing them.

See [LICENSE](LICENSE) for the full project license.
