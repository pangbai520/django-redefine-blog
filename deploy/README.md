# Production notes

These files are starting points for a small Ubuntu server using PostgreSQL, Gunicorn, systemd and Nginx. Replace every `/srv/django-redefine-blog` and `example.com` value before installing them.

```sh
python -m pip install -r requirements-production.txt
python manage.py check --deploy --settings=config.settings_production
python manage.py migrate --settings=config.settings_production
python manage.py collectstatic --noinput --settings=config.settings_production
sudo systemctl restart django-redefine-blog
curl --fail https://example.com/health/
```

Copy `.env.example` to `/etc/django-redefine-blog.env`, fill in real values and restrict it to the service account. Enable `django-redefine-blog-backup.timer` only after `/srv/backups/django-redefine-blog` is writable by `www-data`.

Backups contain database content and uploaded media, but not environment secrets. Copy them off the server and test a restore before launch:

```sh
python manage.py import_blog /path/to/blog-backup-YYYYMMDD-HHMMSS.zip --replace
```
