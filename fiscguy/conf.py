"""Runtime settings. Every value is read at call time so settings can be overridden in tests."""

from django.conf import settings
from django.utils.module_loading import import_string

DEFAULT_PERMISSION_CLASSES = ["rest_framework.permissions.IsAdminUser"]
CLOSE_POLL_MODES = ("background", "client")


def ui_enabled() -> bool:
    return bool(getattr(settings, "FISCGUY_UI_ENABLED", False))


def permission_classes() -> list:
    paths = getattr(settings, "FISCGUY_PERMISSION_CLASSES", DEFAULT_PERMISSION_CLASSES)
    return [import_string(p) if isinstance(p, str) else p for p in paths]


def close_poll_mode() -> str:
    mode = getattr(settings, "FISCGUY_CLOSE_POLL", "background")
    return mode if mode in CLOSE_POLL_MODES else "background"


def log_fdms_payloads() -> bool:
    return bool(getattr(settings, "FISCGUY_LOG_FDMS_PAYLOADS", False))


def reauth_max_age() -> int:
    return int(getattr(settings, "FISCGUY_REAUTH_MAX_AGE", 300))


def _hook(name):
    hook = getattr(settings, name, None)
    return import_string(hook) if isinstance(hook, str) else hook


def device_queryset(request):
    """Devices the request may act on. FISCGUY_DEVICE_QUERYSET(request) lets the host scope them."""
    from fiscguy.models import Device

    hook = _hook("FISCGUY_DEVICE_QUERYSET")
    return hook(request) if hook else Device.objects.all()


def scope_to_devices(request, queryset, field: str = "device"):
    """Restrict a device-owned queryset to the request's devices when a host hook is set."""
    if _hook("FISCGUY_DEVICE_QUERYSET") is None:
        return queryset
    return queryset.filter(**{f"{field}__in": device_queryset(request)})


def access_allowed(request, action: str) -> bool:
    """Web UI gate. FISCGUY_ACCESS_CHECK(request, action) replaces the default permission check."""
    user = request.user
    if not user.is_authenticated or not user.is_active:
        return False
    hook = _hook("FISCGUY_ACCESS_CHECK")
    if hook:
        return bool(hook(request, action))
    return user.has_perm(f"fiscguy.{action}")
