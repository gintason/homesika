"""
Homesika settings shared by every environment. All configuration comes from environment
variables (see .env.example); nothing secret lives in the repo.
"""

from datetime import timedelta
from pathlib import Path

import environ
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parents[2]
env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env", overwrite=False)

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])
ADMIN_URL = env("DJANGO_ADMIN_URL", default="admin/")
API_DOCS_ENABLED = env.bool("API_DOCS_ENABLED", default=False)

INSTALLED_APPS = [
    "daphne",  # ASGI server for Channels; must precede staticfiles
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "drf_spectacular",
    "django_celery_beat",
    "channels",
    # Homesika
    "apps.core",
    "apps.accounts",
    "apps.notifications",
    "apps.orgs",
    "apps.properties",
    "apps.leasing",
    "apps.payments",
    "apps.accounting",
]

AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "apps.core.middleware.RequestIdMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["ATOMIC_REQUESTS"] = False
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    }
}
CHANNEL_LAYERS = {
    "default": {"BACKEND": "channels_redis.core.RedisChannelLayer", "CONFIG": {"hosts": [REDIS_URL]}}
}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

# Localisation: English and Nigerian Pidgin at launch, French later.
LANGUAGE_CODE = "en"
LANGUAGES = [("en", "English"), ("pcm", "Nigerian Pidgin"), ("fr", "Français")]
LOCALE_PATHS = [BASE_DIR / "locale"]
USE_I18N = True
TIME_ZONE = env("TIME_ZONE", default="Africa/Lagos")
USE_TZ = True

# Defaults for new organizations (configurable per org for expansion).
DEFAULT_COUNTRY = env("DEFAULT_COUNTRY", default="NG")
DEFAULT_CURRENCY = env("DEFAULT_CURRENCY", default="NGN")

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework_simplejwt.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.exceptions.homesika_exception_handler",
    "DEFAULT_THROTTLE_RATES": {
        "anon": env("THROTTLE_ANON", default="30/min"),
        "user": env("THROTTLE_USER", default="120/min"),
        "auth": env("THROTTLE_AUTH", default="5/min"),
        "otp": env("THROTTLE_OTP", default="10/min"),
        "pin_login": env("THROTTLE_PIN_LOGIN", default="20/min"),
        "pin": env("THROTTLE_PIN", default="10/hour"),
        "pay": env("THROTTLE_PAY", default="30/min"),
    },
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardCursorPagination",
}
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_ACCESS_MINUTES", default=10)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("JWT_REFRESH_DAYS", default=7)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": False,
    "ALGORITHM": "HS512",
    "SIGNING_KEY": env("JWT_SIGNING_KEY", default=SECRET_KEY),
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# Login PIN (6 digits), transaction PIN (4 digits) and one-time codes.
LOGIN_PIN_MAX_ATTEMPTS = env.int("LOGIN_PIN_MAX_ATTEMPTS", default=5)
LOGIN_PIN_LOCKOUT_MINUTES = env.int("LOGIN_PIN_LOCKOUT_MINUTES", default=30)
TRANSACTION_PIN_MAX_ATTEMPTS = env.int("TRANSACTION_PIN_MAX_ATTEMPTS", default=5)
TRANSACTION_PIN_LOCKOUT_MINUTES = env.int("TRANSACTION_PIN_LOCKOUT_MINUTES", default=30)
PIN_SETUP_TOKEN_SECONDS = 15 * 60
OTP_TTL_MINUTES = env.int("OTP_TTL_MINUTES", default=10)
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_SECONDS = env.int("OTP_RESEND_SECONDS", default=60)
OTP_MAX_SENDS = 5
OTP_MAX_PER_HOUR = env.int("OTP_MAX_PER_HOUR", default=8)

# SMS: "mock" (logs only, nothing sent) until a provider is configured; "termii" for real.
SMS_PROVIDER = env("SMS_PROVIDER", default="mock")
TERMII_API_KEY = env("TERMII_API_KEY", default="")
TERMII_SENDER_ID = env("TERMII_SENDER_ID", default="Homesika")
TERMII_CHANNEL = env("TERMII_CHANNEL", default="dnd")
TERMII_BASE_URL = env("TERMII_BASE_URL", default="https://api.ng.termii.com")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="Homesika <no-reply@homesika.com>")

# Where links in SMS/WhatsApp point (the web app hosts the public pay page).
WEB_APP_URL = env("WEB_APP_URL", default="http://localhost:5173")

# Payments: gateways tried in this order (failover). "mock" moves no money and is refused in production.
PAYMENT_GATEWAYS = env("PAYMENT_GATEWAYS", default="mock")
PAYMENT_LINK_TTL_HOURS = env.int("PAYMENT_LINK_TTL_HOURS", default=72)
# Homesika's fee per rent/dues payment (percent, capped; kobo). 0 = everything settles to the landlord.
PLATFORM_FEE_PERCENT = env("PLATFORM_FEE_PERCENT", default="0")
PLATFORM_FEE_CAP = env.int("PLATFORM_FEE_CAP", default=0)
PAYSTACK_SECRET_KEY = env("PAYSTACK_SECRET_KEY", default="")
PAYSTACK_BASE_URL = env("PAYSTACK_BASE_URL", default="https://api.paystack.co")
FLUTTERWAVE_SECRET_KEY = env("FLUTTERWAVE_SECRET_KEY", default="")
FLUTTERWAVE_WEBHOOK_HASH = env("FLUTTERWAVE_WEBHOOK_HASH", default="")
FLUTTERWAVE_BASE_URL = env("FLUTTERWAVE_BASE_URL", default="https://api.flutterwave.com/v3")

SPECTACULAR_SETTINGS = {
    "TITLE": "Homesika API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # Many models have a "status" field; give each choice set its own schema name.
    "ENUM_NAME_OVERRIDES": {
        "MembershipStatusEnum": "apps.orgs.models.Membership.Status",
        "UnitStatusEnum": "apps.properties.models.Unit.Status",
        "LeaseStatusEnum": "apps.leasing.models.Lease.Status",
        "ChargeStatusEnum": "apps.leasing.models.Charge.Status",
        "SettlementAccountStatusEnum": "apps.payments.models.SettlementAccount.Status",
        "PaymentLinkStatusEnum": "apps.payments.models.PaymentLink.Status",
        "PaymentStatusEnum": "apps.payments.models.Payment.Status",
        "DataRequestStatusEnum": "apps.accounts.models.DataRequest.Status",
    },
}

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = None
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_DEFAULT_QUEUE = "default"
# Panic-alert fan-out gets its own queue and workers so nothing can delay it (Phase 5).
CELERY_TASK_ROUTES = {"apps.security.tasks.*": {"queue": "alerts"}}
CELERY_TIMEZONE = TIME_ZONE  # beat crontabs below are Lagos time
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_BEAT_SCHEDULE = {
    "payments-reconcile-pending": {
        "task": "apps.payments.tasks.reconcile_pending_links",
        "schedule": 15 * 60.0,
    },
    "payments-daily-reconciliation": {
        "task": "apps.payments.tasks.daily_reconciliation",
        "schedule": crontab(hour=6, minute=7),
    },
    "payments-rent-reminders": {
        "task": "apps.payments.tasks.send_rent_reminders",
        "schedule": crontab(hour=9, minute=3),  # TIME_ZONE (Lagos): a sensible hour to receive an SMS
    },
}

# AES-256-GCM keys for encrypted columns (base64 of 32 bytes; first key encrypts, all decrypt).
FIELD_ENCRYPTION_KEYS = env.list("FIELD_ENCRYPTION_KEYS", default=[])

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"request_id": {"()": "apps.core.middleware.RequestIdFilter"}},
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.json.JsonFormatter",
            "fmt": "%(asctime)s %(levelname)s %(name)s %(request_id)s %(message)s",
        },
        "plain": {"format": "%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": env("LOG_FORMAT", default="json"),
            "filters": ["request_id"],
        }
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
}

SENTRY_DSN = env("SENTRY_DSN", default="")
