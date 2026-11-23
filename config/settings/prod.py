from .base import *  # noqa: F403

DEBUG = False

if SECRET_KEY == "unsafe-development-key-change-me":  # noqa: F405
    raise RuntimeError("Set SECRET_KEY in the production environment.")

if not ALLOWED_HOSTS:  # noqa: F405
    raise RuntimeError("Set ALLOWED_HOSTS in the production environment.")

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
