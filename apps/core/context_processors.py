from django.conf import settings


def pwa(request):
    return {
        "VAPID_PUBLIC_KEY": settings.VAPID_PUBLIC_KEY,
        "EDMS_APP_NAME": "Effective Diet Management System",
    }
