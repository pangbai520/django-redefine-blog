# Contributing

Bug reports and focused pull requests are welcome. Before opening an issue,
please check whether the problem comes from this Django port or from the
upstream Redefine theme. Links to the affected page, browser details and a small
reproduction are much more useful than a screenshot on its own.

For code changes:

1. create a branch from the current default branch;
2. keep unrelated formatting changes out of the patch;
3. add or update a regression test when behavior changes;
4. run the Django and frontend checks below;
5. explain any intentional difference from Redefine in the pull request.

```bash
python manage.py check
python manage.py test blog
python manage.py makemigrations --check --dry-run
cd ..
node --test tests/frontend-regressions.cjs
```

The project follows Redefine's DOM and interaction model where that still makes
sense in Django. A port does not have to preserve Hexo-only machinery, but it
should not replace an existing theme behavior without a concrete reason.

Please do not commit databases, `.env` files, uploads, export archives or
production logs. Third-party assets must keep their copyright and license
notices.
