# Contributing

If something is broken, open an issue with the page URL, browser version and the
steps that reproduce it. A screenshot helps with visual differences; a traceback
or response body helps with server errors.

Keep pull requests to one change when possible. Behaviour changes should include
a regression test. Before submitting, run:

```bash
python manage.py check
python manage.py test blog
python manage.py makemigrations --check --dry-run
node --test tests/frontend-regressions.cjs
```

This project follows Redefine where the same behaviour makes sense in Django.
If a pull request intentionally looks or behaves differently from the upstream
theme, explain why.

Do not commit `.env`, databases, uploads, backups or production logs.
