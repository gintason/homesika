"""Production: HTTPS only, hardened cookies and headers, Sentry, JSON logs."""

import sentry_sdk
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import SENTRY_DSN, env

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SECURE_REDIRECT_EXEMPT = [r"^health/"]
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "DENY"
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# Render sets RENDER_EXTERNAL_HOSTNAME (e.g. homesika-api.onrender.com). TODO(verify) on first deploy.
_render_host = env("RENDER_EXTERNAL_HOSTNAME", default="")
if _render_host:
    ALLOWED_HOSTS = [*ALLOWED_HOSTS, _render_host]  # noqa: F405
    CSRF_TRUSTED_ORIGINS = [*CSRF_TRUSTED_ORIGINS, f"https://{_render_host}"]

STORAGES["staticfiles"] = {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"}  # noqa: F405

ENVIRONMENT = env("ENVIRONMENT", default="production")

# The mock gateway moves no money: it must never be enabled in production.
if ENVIRONMENT == "production" and "mock" in PAYMENT_GATEWAYS:  # noqa: F405
    raise ImproperlyConfigured("PAYMENT_GATEWAYS must not include 'mock' in production.")
# The mock assistant and mock WhatsApp reply "MOCK:" / send nothing: never to real users.
if ENVIRONMENT == "production" and ASSISTANT_PROVIDER == "mock":  # noqa: F405
    raise ImproperlyConfigured("ASSISTANT_PROVIDER must not be 'mock' in production.")
if ENVIRONMENT == "production" and WHATSAPP_PROVIDER == "mock":  # noqa: F405
    raise ImproperlyConfigured("WHATSAPP_PROVIDER must be 'cloud' or 'off' in production.")
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=ENVIRONMENT,
        traces_sample_rate=env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.05),
        send_default_pii=False,  # NDPA: never ship personal data to the error tracker
    )
