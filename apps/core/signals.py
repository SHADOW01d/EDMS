from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from .models import AuditEvent


def _request_context(request):
    if request is None:
        return None, "", ""
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    ip_address = forwarded_for.split(",", 1)[0].strip() if forwarded_for else request.META.get("REMOTE_ADDR")
    user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]
    return ip_address, user_agent, request.path[:500]


@receiver(user_logged_in)
def audit_login(sender, request, user, **kwargs):
    ip_address, user_agent, request_path = _request_context(request)
    AuditEvent.objects.create(
        actor=user,
        category=AuditEvent.Category.AUTHENTICATION,
        action="login.success",
        ip_address=ip_address,
        user_agent=user_agent,
        request_path=request_path,
    )


@receiver(user_logged_out)
def audit_logout(sender, request, user, **kwargs):
    ip_address, user_agent, request_path = _request_context(request)
    AuditEvent.objects.create(
        actor=user,
        category=AuditEvent.Category.AUTHENTICATION,
        action="logout.success",
        ip_address=ip_address,
        user_agent=user_agent,
        request_path=request_path,
    )


@receiver(user_login_failed)
def audit_failed_login(sender, credentials, request, **kwargs):
    ip_address, user_agent, request_path = _request_context(request)
    username = str(credentials.get("username", ""))[:150]
    AuditEvent.objects.create(
        category=AuditEvent.Category.AUTHENTICATION,
        action="login.failed",
        object_type="User",
        object_id=username,
        previous_values={},
        new_values={"username": username},
        ip_address=ip_address,
        user_agent=user_agent,
        request_path=request_path,
    )
