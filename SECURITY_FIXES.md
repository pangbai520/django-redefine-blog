# Security fixes — 2026-11-10

Applies to the source snapshot based on `95cd1981a700ec62274338dc5962cb63a64dffc5`.

- Public email activation now requires an existing pending registration and
  rejects staff and superusers. Activation tokens use a separate signing salt
  and bind to the pending registration. Saving an existing inactive account
  revokes pending activation. Account activation is serialized using a user-row
  lock on databases that support row locking.
- Site configuration deletion now requires Django's model delete permission,
  in addition to the existing active/last-configuration safeguards.
- Editing a comment in manual-review mode returns it to review. Previously held
  comments stay held even if auto approval is later enabled. The editor displays
  the review status. Disabled comments cannot be edited, and edits are limited.
- The profile form validates the original avatar before decoding, cropping or
  replacing it. Byte, dimension and pixel/frame limits therefore apply to the
  source image as well as the final upload. Image-bomb warnings/errors become
  validation errors.
- One middleware now protects admin, HTML and AJAX password-login routes with
  shared IP/account limits. Responses over the limit return HTTP 429 and a
  Retry-After header. CSRF protection remains in place.

## Upgrade notes

No database schema migration is required. Restart every application worker
after updating the code. Existing email activation links issued before this
change are intentionally invalid; legitimate pending users can request a new
link by signing in with their existing credentials. Password reset tokens and
active accounts retain their existing behavior.

Use Redis or another shared cache for multiple workers; see `DEPLOYMENT.md`.
The code does not provision or inspect production infrastructure. Administrators
should deactivate accounts through Django Admin or `User.save()` so pending
activation is revoked; custom bulk SQL/QuerySet updates must explicitly revoke
pending registrations too, because those updates bypass Django save signals.

## Validation

Regression tests are in `blog/testsuite/test_security_regressions.py`:

```sh
python manage.py test blog --settings=config.settings_test
python manage.py makemigrations --check --dry-run --settings=config.settings_test
node --test tests/frontend-regressions.cjs
```

Production rollout requires restarting the application workers and configuring
a shared cache when running multiple workers, as described above.
