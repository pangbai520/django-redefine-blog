# Deployment

The repository includes examples for a small Linux server running PostgreSQL,
Gunicorn, systemd and Nginx. They assume the project lives at
`/srv/django-redefine-blog`; change that path and `example.com` before using
them.

## Environment

Copy `.env.example` to `/etc/django-redefine-blog.env` and replace every sample
value. At minimum, set:

```env
DJANGO_SECRET_KEY=a-long-random-value
DJANGO_ALLOWED_HOSTS=example.com,www.example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://example.com,https://www.example.com
DB_ENGINE=postgresql
DB_NAME=django_blog
DB_USER=django_blog
DB_PASSWORD=change-me
DB_HOST=127.0.0.1
```

Django does not read this file on its own. The supplied systemd unit loads it
with `EnvironmentFile=`. Keep it outside the repository and make it readable
only by the service account.

For SMTP on port 587, set `EMAIL_USE_TLS=1` and `EMAIL_USE_SSL=0`. Servers using
implicit TLS on port 465 can use `blog.email_backend.SMTPSSLBackend` with
`EMAIL_USE_SSL=1` and `EMAIL_USE_TLS=0`.

## Install and update

Create a virtual environment in the project directory and install the
production requirements:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-production.txt
```

Load the environment in the deployment shell, then prepare Django:

```bash
set -a
. /etc/django-redefine-blog.env
set +a

python manage.py check --deploy --settings=config.settings_production
python manage.py migrate --settings=config.settings_production
python manage.py collectstatic --noinput --settings=config.settings_production
python manage.py rebuild_search_index --settings=config.settings_production
```

Install the supplied service and Nginx configuration after editing their paths
and domain names:

```bash
sudo cp deploy/django-redefine-blog.service /etc/systemd/system/
sudo cp deploy/nginx.conf.example /etc/nginx/sites-available/django-redefine-blog
sudo ln -s /etc/nginx/sites-available/django-redefine-blog /etc/nginx/sites-enabled/
sudo systemctl daemon-reload
sudo systemctl enable --now django-redefine-blog
sudo nginx -t
sudo systemctl reload nginx
```

Check `https://example.com/health/` after each deployment. The endpoint verifies
that Django can reach the database.

`STATIC_ROOT` and `MEDIA_ROOT` should be outside the checkout and writable by
the service account. Nginx serves both directly; never configure it to execute
anything below the media directory.

## Backups

`backup_blog` creates a timestamped zip containing database content and uploaded
media:

```bash
python manage.py backup_blog --directory /srv/backups/django-redefine-blog
```

The included systemd timer runs this command daily. A backup still contains
password hashes and private site data, so copy it off the server and protect it
like the database itself.

To restore into a migrated installation:

```bash
python manage.py import_blog /path/to/blog-backup.zip --replace
```

Test that procedure before relying on the timer.

For the container setup, see [OPTIONAL_FEATURES.md](OPTIONAL_FEATURES.md).
