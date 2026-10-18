# Production deployment checklist

Set these environment variables before starting Django in production:

```text
DJANGO_SECRET_KEY=<long-random-secret>
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=example.com,www.example.com
EMAIL_HOST_USER=<mailbox>
EMAIL_HOST_PASSWORD=<mail-password>
```

The development default writes mail to the console. Configure a real provider
without changing source code:

```text
DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_USE_SSL=0
EMAIL_USE_TLS=1
EMAIL_TIMEOUT=10
DEFAULT_FROM_EMAIL=Blog <blog@example.com>
```

Use either SSL or TLS, never both. Account verification treats delivery failure
as a failed registration and removes the inactive account, comment notification
mail is best-effort and never rolls back a successfully posted comment.

Providers that require implicit SSL on port 465 can use the included backend:

```text
DJANGO_EMAIL_BACKEND=blog.email_backend.SMTPSSLBackend
EMAIL_PORT=465
EMAIL_USE_SSL=1
EMAIL_USE_TLS=0
```

The project serves uploaded comment images from `MEDIA_ROOT` (`blog/resources`)
under `MEDIA_URL` (`/resources/`). Keep this directory writable by the web
process, but do not expose the application source tree. Configure the reverse
proxy/web server to serve `/resources/` as static media and apply a non-executable
content policy for that location (for example, disable script execution and
force image content types).

Run `python manage.py collectstatic --noinput` during deployment. Static assets
are collected from `blog/static`, the previous missing `static` directory warning
has been removed.

Install Pillow in the runtime environment (`pip install Pillow`), comment image
uploads use it to verify the file's actual format before storage.

## Before making the repository public

Publish only placeholder mail values and keep the real mailbox and authorization
code in the deployment environment. Scan the Git history as well as the current
tree and rotate any credential that was ever committed.

Keep `.env` files, database files, `blog/resources`, exported archives and
production logs out of the public repository. An `.env.example` may document
required variable names, but it must contain only values such as
`smtp.example.com`, `blog@example.com` and obvious non-secret placeholders.

## Portable backups

From the repository root, create an archive containing content,
configuration, user accounts and uploaded files:

```text
python manage.py export_blog blog-backup.zip
```

Traffic rows are excluded by default because they grow continuously. Include
them only when needed:

```text
python manage.py export_blog blog-backup.zip --include-traffic
```

After running migrations on a new installation, restore the archive with:

```text
python manage.py import_blog blog-backup.zip
```

An existing blog is refused by default. `--replace` deletes existing blog rows
before restoring, while preserving unrelated project data. Imported users are
matched by username. Media files from the archive overwrite matching paths but
do not delete unrelated files.

The archive contains password hashes, private configuration and uploads. Store
it as a secret, copy it off the server, and test restoration periodically.
