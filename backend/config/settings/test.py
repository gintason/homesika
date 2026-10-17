import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-secret-key-not-for-production-" + "x" * 40)
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FIELD_ENCRYPTION_KEYS", "dGVzdC1vbmx5LWtleS1kby1ub3QtdXNlLTMyYnl0ZXM=")
os.environ.setdefault("SMS_PROVIDER", "mock")
os.environ.setdefault("WHATSAPP_PROVIDER", "mock")
os.environ.setdefault("ASSISTANT_PROVIDER", "mock")

from .base import *  # noqa: E402, F403

DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # fast tests only
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
LOGGING["handlers"]["console"]["formatter"] = "plain"  # noqa: F405
MIDDLEWARE = [m for m in MIDDLEWARE if "whitenoise" not in m]  # noqa: F405 - no collected static in tests
