<div align="right">
  <img src="https://img.shields.io/badge/-English-A31F34?style=for-the-badge" alt="English">
  <a href="README_zh-CN.md"><img src="https://img.shields.io/badge/-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-545759?style=for-the-badge" alt="简体中文"></a>
  <a href="README_zh-TW.md"><img src="https://img.shields.io/badge/-%E7%B9%81%E9%AB%94%E4%B8%AD%E6%96%87-545759?style=for-the-badge" alt="繁體中文"></a>
</div>

<p align="center">
  <img width="92" src="blog/static/images/redefine-logo.webp" alt="Redefine logo">
</p>

<h1 align="center">django-redefine-blog</h1>

<p align="center">A Django blog based on Redefine.</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12%E2%80%933.14-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.12 to 3.14">
  <img src="https://img.shields.io/badge/Django-6.0-0C4B33?style=flat-square&logo=django&logoColor=white" alt="Django 6.0">
  <img src="https://img.shields.io/badge/license-GPL--3.0-A31F34?style=flat-square" alt="GPL-3.0">
</p>

This project brings the look and browser-side behaviour of
[hexo-theme-redefine](https://github.com/EvanNotFound/hexo-theme-redefine) to a
regular Django application. Articles, comments, menus and site settings live in
the database and are edited through Django Admin.

It is a standalone blog application, not a theme that can be installed into an
existing Hexo site.

## What is included

- Redefine-style home, post, archive, category and tag pages, plus Friends,
  Bookmarks, Essays and Masonry pages
- Markdown rendering with Redefine's commonly used callouts, folding blocks,
  tabs, buttons and code blocks
- drafts, scheduled posts, related posts, RSS, Sitemap and server-side search
- a built-in comment system with accounts, replies, likes, moderation, badges,
  emoji, GIF search and image uploads
- light/dark mode, Swup navigation and seven interface languages
- SQLite for a quick local setup, with PostgreSQL and MySQL configuration for
  deployment

Waline, Gitalk, Twikoo and Giscus can still be used instead of the built-in
comments.

## Quick start

Python 3.12 through 3.14 are supported.

```bash
python -m venv .venv
```

Activate the environment with `.venv\Scripts\Activate.ps1` in PowerShell, or
`source .venv/bin/activate` on Linux and macOS. Then run:

```bash
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

The blog is now available at `http://127.0.0.1:8000/`; Django Admin is at
`http://127.0.0.1:8000/admin/`.

The first migration installs a starter configuration and article so that a new
checkout is not an empty page. Both can be changed or removed from the admin.
Development uses SQLite and writes email to the terminal.

## Deployment

Do not use `runserver` for a public site. Production settings are read from the
environment; [.env.example](.env.example) lists the available variables.

[DEPLOYMENT.md](DEPLOYMENT.md) covers the included Gunicorn, systemd and Nginx
files. Docker Compose, Redis and GitHub login are described in
[OPTIONAL_FEATURES.md](OPTIONAL_FEATURES.md).

## Tests

```bash
python manage.py check
python manage.py test blog
python manage.py makemigrations --check --dry-run
node --test tests/frontend-regressions.cjs
```

Node.js is only needed for the frontend tests; the site has no frontend build
step.

## Credits

The frontend is based on
[hexo-theme-redefine](https://github.com/EvanNotFound/hexo-theme-redefine) by
[EvanNotFound](https://github.com/EvanNotFound) and its contributors. This
repository is released under GPL-3.0. Bundled third-party files keep their own
licences; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
