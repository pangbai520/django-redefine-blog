# systemd and Nginx files

These files are examples for a small Ubuntu deployment. They use
`/srv/django-redefine-blog`, run Django as `www-data` and expect the environment
file at `/etc/django-redefine-blog.env`. Edit those values before copying the
files into `/etc`.

The supplied Nginx configuration keeps `client_max_body_size` slightly above
`AUDIO_UPLOAD_MAX_BYTES`. This lets Django and the admin-side file check show a
translated validation message instead of Nginx replacing the page with a bare
413 response. Proxies in front of Nginx may impose a lower independent limit;
for example, Cloudflare Free and Pro accept request bodies up to 100 MB.

After an update:

```bash
. .venv/bin/activate
set -a; . /etc/django-redefine-blog.env; set +a
python manage.py check --deploy --settings=config.settings_production
python manage.py migrate --settings=config.settings_production
python manage.py collectstatic --noinput --settings=config.settings_production
python manage.py rebuild_search_index --settings=config.settings_production
sudo systemctl restart django-redefine-blog
curl --fail https://example.com/health/
```

`django-redefine-blog-backup.timer` runs the built-in backup command once a day.
Enable it only after its destination exists and is writable by the service user.
The resulting archives contain private blog data and should be copied off the
server.

The full walkthrough is in [../DEPLOYMENT.md](../DEPLOYMENT.md).
