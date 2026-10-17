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
    "apps.messaging",
    "apps.listings",
    "apps.assistant",
    "apps.bills",
    "apps.artisans",
    "apps.maintenance",
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
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # Private files (repair photos, ID documents): never served directly, only through short-lived signed
    # links checked by the API (apps.core.media).
    "private": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {"location": BASE_DIR / "private_media", "base_url": None},
    },
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
PRIVATE_MEDIA_LINK_SECONDS = env.int("PRIVATE_MEDIA_LINK_SECONDS", default=15 * 60)
# Uploaded files (listing photos) go to S3-compatible storage when a bucket is set; Render's disk is wiped
# on every deploy, so staging and production need this.
S3_BUCKET = env("S3_BUCKET", default="")
if S3_BUCKET:
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": S3_BUCKET,
            "endpoint_url": env("S3_ENDPOINT_URL", default=None),  # e.g. Cloudflare R2's account endpoint
            "access_key": env("S3_ACCESS_KEY_ID", default=None),
            "secret_key": env("S3_SECRET_ACCESS_KEY", default=None),
            "region_name": env("S3_REGION", default="auto"),
            "custom_domain": env("S3_PUBLIC_DOMAIN", default=None),  # public CDN domain for photos
            "querystring_auth": False,
            "file_overwrite": False,
            "default_acl": None,
        },
    }
    # A separate bucket with NO public access. Falls back to the photo bucket under a "private/" prefix
    # (names are random, but the deploy check warns: that bucket is usually public).
    S3_PRIVATE_BUCKET = env("S3_PRIVATE_BUCKET", default="")
    STORAGES["private"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            **{k: v for k, v in STORAGES["default"]["OPTIONS"].items() if k != "custom_domain"},
            "bucket_name": S3_PRIVATE_BUCKET or S3_BUCKET,
            "location": "" if S3_PRIVATE_BUCKET else "private",
            "querystring_auth": True,
            "querystring_expire": PRIVATE_MEDIA_LINK_SECONDS,
        },
    }

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
        "listing": env("THROTTLE_LISTING", default="30/min"),
        "bills": env("THROTTLE_BILLS", default="30/min"),
        "tickets": env("THROTTLE_TICKETS", default="30/hour"),
        "vouch": env("THROTTLE_VOUCH", default="20/hour"),
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
# WhatsApp: "mock" (nothing sent), "cloud" (Meta WhatsApp Cloud API), or "off".
WHATSAPP_PROVIDER = env("WHATSAPP_PROVIDER", default="mock")
WHATSAPP_GRAPH_URL = env("WHATSAPP_GRAPH_URL", default="https://graph.facebook.com")
WHATSAPP_API_VERSION = env("WHATSAPP_API_VERSION", default="v21.0")  # TODO(verify) current version
WHATSAPP_PHONE_NUMBER_ID = env("WHATSAPP_PHONE_NUMBER_ID", default="")
WHATSAPP_ACCESS_TOKEN = env("WHATSAPP_ACCESS_TOKEN", default="")
WHATSAPP_APP_SECRET = env("WHATSAPP_APP_SECRET", default="")
WHATSAPP_VERIFY_TOKEN = env("WHATSAPP_VERIFY_TOKEN", default="")
# Approved message templates per notification kind, e.g.
# {"receipt": {"name": "payment_receipt", "language": "en"}}. Empty = reminders/receipts go by SMS.
WHATSAPP_TEMPLATES = env.json("WHATSAPP_TEMPLATES", default={})
# Where the assistant receives WhatsApp messages (an import path); empty = store only.
MESSAGING_INBOUND_HANDLER = env(
    "MESSAGING_INBOUND_HANDLER", default="apps.assistant.channels.handle_whatsapp"
)
# Escalations with no organization (e.g. a prospect) alert this number.
SUPPORT_PHONE = env("SUPPORT_PHONE", default="")
SUPPORT_HOURS = env("SUPPORT_HOURS", default="Monday to Saturday, 8am to 6pm (Lagos time)")

# AI assistant. "anthropic" uses Claude (needs ANTHROPIC_API_KEY in the environment); "mock" is a labelled
# rule-based stand-in for development and tests.
ASSISTANT_PROVIDER = env("ASSISTANT_PROVIDER", default="mock")
ANTHROPIC_MODEL = env("ANTHROPIC_MODEL", default="claude-opus-5-5")
ASSISTANT_EFFORT_CHAT = env("ASSISTANT_EFFORT_CHAT", default="medium")
ASSISTANT_EFFORT_LISTING = env("ASSISTANT_EFFORT_LISTING", default="medium")
ASSISTANT_MAX_TOKENS = env.int("ASSISTANT_MAX_TOKENS", default=4096)
ASSISTANT_MAX_TOOL_ROUNDS = env.int("ASSISTANT_MAX_TOOL_ROUNDS", default=6)
# Spending caps in USD (cost is estimated from token usage).
ASSISTANT_USER_DAILY_CAP_USD = env("ASSISTANT_USER_DAILY_CAP_USD", default="0.50")
ASSISTANT_ORG_MONTHLY_CAP_USD = env("ASSISTANT_ORG_MONTHLY_CAP_USD", default="30")
ASSISTANT_PLATFORM_DAILY_CAP_USD = env("ASSISTANT_PLATFORM_DAILY_CAP_USD", default="25")
ASSISTANT_RATE_LIMIT = env("ASSISTANT_RATE_LIMIT", default="20/600")  # messages per seconds, per sender
ASSISTANT_PRICES = env.json("ASSISTANT_PRICES", default={})

# Bills (airtime, data, TV, electricity). Providers in failover order; "mock" for development only.
BILLS_PROVIDERS = env("BILLS_PROVIDERS", default="mock")
VTUNG_BASE_URL = env("VTUNG_BASE_URL", default="https://vtu.ng/wp-json")
VTUNG_USERNAME = env("VTUNG_USERNAME", default="")
VTUNG_PASSWORD = env("VTUNG_PASSWORD", default="")
VTUNG_USER_PIN = env("VTUNG_USER_PIN", default="")  # signs VTU.ng webhooks
BILLS_DATA_MARKUP_PERCENT = env.float("BILLS_DATA_MARKUP_PERCENT", default=0.0)
BILLS_TV_MARKUP_PERCENT = env.float("BILLS_TV_MARKUP_PERCENT", default=0.0)
# Kobo per order, by category. Default: NGN 100 on electricity and cable TV, nothing on airtime/data.
BILLS_FEES = env.json("BILLS_FEES", default={"electricity": 100_00, "cable_tv": 100_00})
BILLS_DAILY_LIMIT = env.int("BILLS_DAILY_LIMIT", default=0)  # kobo per person per 24h; 0 = no limit
BILLS_PAYMENT_TTL_MINUTES = env.int("BILLS_PAYMENT_TTL_MINUTES", default=60)
BILLS_STATUS_POLL_SECONDS = env.int("BILLS_STATUS_POLL_SECONDS", default=30)
BILLS_MAX_STATUS_CHECKS = env.int("BILLS_MAX_STATUS_CHECKS", default=12)

# Maintenance and artisans (Phase 4).
# "nin" (default): NIN looked up through NIN_PROVIDER + the ID photo and proof of address read by AI, with
# fixed rules deciding and anything unclear going to a person. "manual": staff review everything.
ID_VERIFICATION_PROVIDER = env("ID_VERIFICATION_PROVIDER", default="nin")
# The licensed NIN lookup provider. Only "mock" exists until one is chosen (apps/artisans/nin.py).
NIN_PROVIDER = env("NIN_PROVIDER", default="mock")
ASSISTANT_EFFORT_VERIFY = env("ASSISTANT_EFFORT_VERIFY", default="medium")
ARTISAN_DOCUMENT_RETENTION_DAYS = env.int("ARTISAN_DOCUMENT_RETENTION_DAYS", default=90)
ARTISAN_PROOF_MAX_AGE_DAYS = env.int("ARTISAN_PROOF_MAX_AGE_DAYS", default=92)  # "last 3 months"
ARTISAN_VOUCHER_LINK_DAYS = env.int("ARTISAN_VOUCHER_LINK_DAYS", default=14)
MAINTENANCE_MAX_PHOTOS = env.int("MAINTENANCE_MAX_PHOTOS", default=6)
MAINTENANCE_OFFER_HOURS = env.int("MAINTENANCE_OFFER_HOURS", default=24)  # artisan must accept within
MAINTENANCE_CONFIRM_REMINDER_DAYS = env.int("MAINTENANCE_CONFIRM_REMINDER_DAYS", default=2)
MAINTENANCE_AUTO_CONFIRM_DAYS = env.int("MAINTENANCE_AUTO_CONFIRM_DAYS", default=7)  # tenant silent -> fixed

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
        "ListingStatusEnum": "apps.listings.models.Listing.Status",
        "ViewingStatusEnum": "apps.listings.models.Viewing.Status",
        "MessageStatusEnum": "apps.messaging.models.Message.Status",
        "ConversationStatusEnum": "apps.messaging.models.Conversation.Status",
        "EscalationStatusEnum": "apps.messaging.models.Escalation.Status",
        "KbArticleStatusEnum": "apps.assistant.models.KbArticle.Status",
        "PendingActionStatusEnum": "apps.assistant.models.PendingAction.Status",
        "ConversationChannelEnum": "apps.messaging.models.Conversation.Channel",
        "ChatChannelEnum": [("app", "app"), ("web", "web")],
        "BillCategoryEnum": "apps.bills.models.Category",
        "BillOrderStatusEnum": "apps.bills.models.Order.Status",
        "OtpChannelEnum": [("sms", "SMS"), ("email", "Email")],
        "TradeEnum": "apps.artisans.models.Trade",
        "ArtisanStatusEnum": "apps.artisans.models.ArtisanProfile.Status",
        "VerificationCheckKindEnum": "apps.artisans.models.VerificationCheck.Kind",
        "VerificationCheckStatusEnum": "apps.artisans.models.VerificationCheck.Status",
        "VoucherKindEnum": "apps.artisans.models.Voucher.Kind",
        "VoucherStatusEnum": "apps.artisans.models.Voucher.Status",
        "TicketStatusEnum": "apps.maintenance.models.Ticket.Status",
        "TicketPriorityEnum": "apps.maintenance.models.Ticket.Priority",
        "TicketChannelEnum": "apps.maintenance.models.Ticket.Channel",
        "TicketEventKindEnum": "apps.maintenance.models.TicketEvent.Kind",
        "TicketPhotoStageEnum": "apps.maintenance.models.TicketPhoto.Stage",
        "JobStatusEnum": "apps.maintenance.models.Job.Status",
        "ManualPaymentChannelEnum": [
            ("cash", "Cash"),
            ("bank_transfer", "Bank transfer"),
            ("pos", "POS"),
            ("cheque", "Cheque"),
        ],
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
    "bills-reconcile": {
        "task": "apps.bills.tasks.reconcile_bills",
        "schedule": 5 * 60.0,
    },
    "artisans-housekeeping": {
        "task": "apps.artisans.tasks.housekeeping",
        "schedule": 60 * 60.0,
    },
    "maintenance-housekeeping": {
        "task": "apps.maintenance.tasks.housekeeping",
        "schedule": 30 * 60.0,
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
