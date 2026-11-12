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

## S3-compatible media storage

Uploads use the local `MEDIA_ROOT` unless another backend is selected. The S3
mode works with AWS S3, Cloudflare R2, MinIO, Backblaze B2, Wasabi and services
that implement the same API. Static theme assets remain local and continue to
be deployed with `collectstatic`.

Install the optional backend when it is not already included by the production
requirements:

```bash
python -m pip install -r requirements-storage.txt
```

Set the service-specific endpoint and credentials outside the repository:

```env
MEDIA_STORAGE=s3
MEDIA_S3_ENDPOINT_URL=https://account-or-service-endpoint.example
MEDIA_S3_BUCKET_NAME=blog-media
MEDIA_S3_ACCESS_KEY_ID=...
MEDIA_S3_SECRET_ACCESS_KEY=...
MEDIA_S3_REGION=auto                 # Cloudflare R2; use the service's region
MEDIA_S3_ADDRESSING_STYLE=path       # optional; depends on the provider
MEDIA_PUBLIC_BASE_URL=https://media.example.com
MEDIA_S3_QUERYSTRING_AUTH=0
```

Use a credential limited to object read/write access on this bucket. The public
domain is only used to read files; uploads and deletes still use the authenticated
S3 endpoint. Browser CORS rules therefore need only `GET` and `HEAD`, not public
write methods.

Run the one-command migration after enabling the backend:

```bash
python manage.py migrate_media_storage --dry-run
python manage.py migrate_media_storage
```

The command copies every file under `MEDIA_ROOT`, checks existing objects, and
rewrites legacy relative `/resources/` links in articles, comments, and custom
pages only when the matching object was included in the migration. A dry run
reports the same counts without uploading files or changing the database. Use
`--skip-url-rewrite` for a copy-only run.

Keep the local files until the public URLs, the image library, audio playback and
a fresh `backup_blog` archive have all been checked. `backup_blog` reads through
Django's active storage backend, so remote images and audio remain part of the
portable archive. The daily orphan cleanup also scans managed remote folders
after the normal database cleanup.

Local files are retained by default as a rollback copy. Add `--delete-local`
only after the migrated site and a fresh backup have been verified. Differing
objects stop the migration unless `--replace` is explicitly supplied.

Advanced deployments may use `MEDIA_STORAGE=custom`, `MEDIA_CUSTOM_BACKEND` and
`MEDIA_CUSTOM_OPTIONS` to supply another Django storage backend. The options are
a JSON object and may contain secrets, so keep them in the protected environment
file rather than the repository.

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
