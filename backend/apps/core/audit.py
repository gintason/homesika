from .models import AuditLog


def client_ip(request) -> str | None:
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (forwarded.split(",")[0].strip() or request.META.get("REMOTE_ADDR")) or None


def record(action: str, *, actor=None, organization=None, obj=None, changes=None, request=None) -> AuditLog:
    """Write one audit row. Never put secrets, PINs or full bank numbers in `changes`."""
    return AuditLog.objects.create(
        action=action,
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        organization=organization,
        object_type=type(obj).__name__ if obj is not None else "",
        object_id=str(getattr(obj, "pk", "")) if obj is not None else "",
        changes=changes or {},
        ip=client_ip(request),
    )
