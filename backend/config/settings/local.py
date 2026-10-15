from .base import *  # noqa: F403
from .base import env

DEBUG = True
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "0.0.0.0"])  # noqa: S104
API_DOCS_ENABLED = True
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS", default=["http://localhost:5173", "http://localhost:8081"]
)
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
LOGGING["handlers"]["console"]["formatter"] = env("LOG_FORMAT", default="plain")  # noqa: F405
