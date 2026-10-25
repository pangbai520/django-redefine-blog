# Optional features

The default `requirements.txt` install uses SQLite, local-memory cache and the
built-in account system. The extras below are opt-in.

## GitHub login

```bash
python -m pip install -r requirements-oauth.txt
```

Create a GitHub OAuth app with this callback URL:

```text
https://your-domain.example/accounts/github/login/callback/
```

Set both variables and run migrations again:

```env
BLOG_GITHUB_OAUTH_CLIENT_ID=...
BLOG_GITHUB_OAUTH_CLIENT_SECRET=...
```

```bash
python manage.py migrate
```

The GitHub button appears in the sign-in dialog only when both values are
present.

## Redis

Local-memory cache is fine for development. Use Redis when several Gunicorn
workers need to share cached search and rendered Markdown results.

```bash
python -m pip install -r requirements-redis.txt
```

```env
CACHE_BACKEND=redis
CACHE_URL=redis://127.0.0.1:6379/1
```

## Docker Compose

Copy `.env.example` to `.env`, replace the sample secrets and run:

```bash
docker compose up -d --build
```

The stack contains Nginx, Django/Gunicorn, PostgreSQL and Redis. Nginx binds to
`127.0.0.1:8000` by default so that a host-level TLS proxy can sit in front of
it. Set `WEB_BIND=0.0.0.0` only when that port is meant to be public.

Named volumes hold the database, cache, static files, media and logs. Back those
volumes up before removing the stack.

## Demo content

To create the same sample content used by the demo site, create a superuser and
then run:

```bash
python manage.py create_demo
```

## Languages

The interface ships in English, Spanish, French, Japanese, Simplified Chinese,
Hong Kong Traditional Chinese and Taiwan Traditional Chinese. Change the site
default with `DJANGO_LANGUAGE_CODE`; readers can choose another language from
the side toolbar.

When a trusted proxy supplies `CF-IPCountry`, `CloudFront-Viewer-Country` or
`X-Country-Code`, a first-time visitor can receive a regional Chinese variant.
The language cookie always takes priority after the reader makes a choice.
