# Web UI and security

Fiscguy ships optional pages for device registration, certificate upload, fiscal day control,
status polling and receipts. They are off by default.

## Enable

```python
# settings.py
INSTALLED_APPS += ["django.contrib.sessions", "django.contrib.messages", "fiscguy"]
FISCGUY_UI_ENABLED = True
FISCGUY_ENCRYPTION_KEY = "<Fernet key>"   # python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# urls.py
path("fiscal/", include("fiscguy.web.urls")),
```

The pages use the host's `LOGIN_URL`. Templates live under `fiscguy/` and can be overridden by
placing files with the same names in your own `templates/fiscguy/` directory.

## Settings

| Setting | Default | Purpose |
|---|---|---|
| `FISCGUY_UI_ENABLED` | `False` | Turns the pages on. When off they return 404. |
| `FISCGUY_PERMISSION_CLASSES` | `["rest_framework.permissions.IsAdminUser"]` | DRF permissions for every JSON endpoint. |
| `FISCGUY_ACCESS_CHECK` | none | `callable(request, action) -> bool` that replaces the page permission check. |
| `FISCGUY_DEVICE_QUERYSET` | none | `callable(request) -> QuerySet[Device]` limiting which devices a request can see or act on. Use it to scope devices per customer, branch or user. |
| `FISCGUY_CLOSE_POLL` | `"background"` | `"client"` stops the server thread; the page (or your frontend) polls `get-status` instead. |
| `FISCGUY_LOG_FDMS_PAYLOADS` | `False` | Logs FDMS request and response bodies at DEBUG. They contain buyer TINs and receipt data. |
| `FISCGUY_REAUTH_MAX_AGE` | `300` | Seconds a password confirmation stays valid. |
| `FISCGUY_ENCRYPTION_KEY` | derived from `SECRET_KEY` | Fernet key for certificate keys and activation keys. |

## Permissions

| Permission | Allows |
|---|---|
| `fiscguy.view_receipts` | Dashboard, device pages, receipts, status and ping |
| `fiscguy.close_day` | Open and close fiscal days |
| `fiscguy.manage_device` | Register devices, upload certificates, renew, sync configuration, audit log |

Superusers have all three. The JSON API is staff-only by default because it can submit receipts
and close days; the old behaviour of open endpoints is gone. Set `FISCGUY_PERMISSION_CLASSES` to
use your own classes.

## What protects the pages

- Feature flag, login and a specific permission on every view. Nothing is public.
- Device lookups go through `FISCGUY_DEVICE_QUERYSET`, so a guessed device or receipt ID returns 404.
- Every state change is POST-only with CSRF protection.
- Registering, uploading certificates and renewing certificates need the user's password again
  (valid for `FISCGUY_REAUTH_MAX_AGE` seconds). Switching a device between test and production
  deletes its history and needs the device ID typed to confirm.
- Per-user throttling on registration, actions, status, ping and password confirmation.
- Responses carry `Cache-Control: no-store`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`
  and a CSP that allows only same-origin scripts and styles. The templates have no inline script or style.
- Keys and activation keys are write-only: never rendered back (even on a failed form), never logged,
  encrypted at rest. Uploads are capped at 64 KB, read in memory, validated and never written to disk.
- Passphrase-protected keys, expired certificates and key/certificate mismatches are rejected.
- Every register, upload, renew, open day and close day is written to `AuditLog` (user, time, device, IP).
  The log is read-only in the Django admin.

`manage.py check` warns when `FISCGUY_ENCRYPTION_KEY` is unset (`fiscguy.W001`) and when the UI is
enabled without secure cookies (`fiscguy.W002`).

## Close day without a background thread

With `FISCGUY_CLOSE_POLL = "client"`, `POST close-day/` returns as soon as FDMS accepts the request.
Poll `GET get-status/` (API) or `devices/<id>/status/` (UI) until the day is `closed` or `close_failed`.
The device page does this automatically.
