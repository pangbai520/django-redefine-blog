# Security

Please report vulnerabilities with GitHub's private security advisory feature,
not a public issue. Include the affected route or feature, a small reproduction
and the impact. Do not attach real user data, `.env` files, database backups,
OAuth secrets or mail credentials.

Security fixes are made against the current `main` branch. Before reporting a
deployment warning, run:

```bash
python manage.py check --deploy --settings=config.settings_production
```
