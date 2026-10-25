from loguru import logger

from fiscguy.models import AuditLog


def client_ip(request) -> str | None:
    return request.META.get("REMOTE_ADDR") or None


def record(request, action: str, device=None, detail: str = "") -> None:
    """Write an audit row. Never raises and never receives key material."""
    try:
        user = getattr(request, "user", None)
        authed = bool(user and user.is_authenticated)
        AuditLog.objects.create(
            actor=user if authed else None,
            actor_name=(user.get_username() if authed else "")[:150],
            action=action[:64],
            device=device,
            device_ref=(device.device_id if device else "")[:100],
            detail=detail[:255],
            ip_address=client_ip(request),
        )
    except Exception:
        logger.exception(f"Failed to write audit log for {action}")
