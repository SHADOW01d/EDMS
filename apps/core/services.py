from .models import AuditEvent


def record_audit_event(
    *,
    actor=None,
    category,
    action,
    object_type="",
    object_id="",
    previous_values=None,
    new_values=None,
    request=None,
):
    ip_address = None
    user_agent = ""
    request_path = ""
    if request is not None:
        forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        ip_address = (forwarded_for.split(",", 1)[0].strip() if forwarded_for else request.META.get("REMOTE_ADDR"))
        user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]
        request_path = request.path[:500]
    return AuditEvent.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        category=category,
        action=action,
        object_type=object_type,
        object_id=str(object_id),
        previous_values=previous_values or {},
        new_values=new_values or {},
        ip_address=ip_address,
        user_agent=user_agent,
        request_path=request_path,
    )
