from django.conf import settings
from django.core.checks import Warning, register

from fiscguy import conf


@register()
def fiscguy_security_checks(app_configs, **kwargs):
    messages = []
    if not getattr(settings, "FISCGUY_ENCRYPTION_KEY", None):
        messages.append(
            Warning(
                "FISCGUY_ENCRYPTION_KEY is not set; certificate keys and activation keys are "
                "encrypted with a key derived from SECRET_KEY.",
                hint="Set a dedicated Fernet key in FISCGUY_ENCRYPTION_KEY and keep it out of the database backups.",
                id="fiscguy.W001",
            )
        )
    if conf.ui_enabled() and not settings.DEBUG:
        if not getattr(settings, "SESSION_COOKIE_SECURE", False) or not getattr(
            settings, "CSRF_COOKIE_SECURE", False
        ):
            messages.append(
                Warning(
                    "FISCGUY_UI_ENABLED is on but SESSION_COOKIE_SECURE or CSRF_COOKIE_SECURE is off.",
                    hint="Serve the UI over HTTPS and set both to True.",
                    id="fiscguy.W002",
                )
            )
    return messages
