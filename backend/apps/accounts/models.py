from datetime import timedelta

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel

from .exceptions import (
    InvalidLoginPIN,
    InvalidTransactionPIN,
    LoginPINLocked,
    TransactionPINLocked,
    TransactionPINNotSet,
)
from .managers import UserManager
from .validators import login_pin_validator, phone_validator, transaction_pin_validator


class User(AbstractBaseUser, PermissionsMixin, TimeStampedModel):
    """Everyone: landlords, agents, tenants, residents, artisans, security, staff.

    What a user may see is decided by memberships (staff roles) and by data links
    (lease, estate membership, job), never by a role field on the user.
    """

    phone_number = models.CharField(
        _("phone number"), max_length=16, unique=True, validators=[phone_validator]
    )
    # NULL (not "") when absent, so the case-insensitive unique constraint ignores users without email.
    email = models.EmailField(_("email address"), null=True, blank=True)  # noqa: DJ001
    first_name = models.CharField(_("first name"), max_length=80, blank=True)
    last_name = models.CharField(_("last name"), max_length=80, blank=True)
    country = models.CharField(_("country"), max_length=2, default="NG", help_text="ISO 3166-1 alpha-2")
    preferred_language = models.CharField(max_length=5, choices=settings.LANGUAGES, default="en")

    is_phone_verified = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False, help_text=_("Homesika platform staff (admin site)."))

    # 6-digit login PIN (replaces a password for app users) and 4-digit transaction PIN (approves money).
    login_pin = models.CharField(max_length=128, blank=True, editable=False)
    login_pin_failed_attempts = models.PositiveSmallIntegerField(default=0, editable=False)
    login_pin_locked_until = models.DateTimeField(null=True, blank=True, editable=False)
    transaction_pin = models.CharField(max_length=128, blank=True, editable=False)
    pin_failed_attempts = models.PositiveSmallIntegerField(default=0, editable=False)
    pin_locked_until = models.DateTimeField(null=True, blank=True, editable=False)

    objects = UserManager()

    USERNAME_FIELD = "phone_number"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("email"), condition=Q(email__isnull=False), name="user_email_ci_unique"
            )
        ]

    def __str__(self):
        return self.full_name or self.phone_number

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    # ---- PINs ----------------------------------------------------------------
    @property
    def has_login_pin(self) -> bool:
        return bool(self.login_pin)

    @property
    def has_transaction_pin(self) -> bool:
        return bool(self.transaction_pin)

    def set_login_pin(self, raw_pin: str) -> None:
        login_pin_validator(raw_pin)
        self.login_pin = make_password(raw_pin)
        self.login_pin_failed_attempts, self.login_pin_locked_until = 0, None
        self.save(
            update_fields=["login_pin", "login_pin_failed_attempts", "login_pin_locked_until", "updated_at"]
        )

    def set_transaction_pin(self, raw_pin: str) -> None:
        transaction_pin_validator(raw_pin)
        self.transaction_pin = make_password(raw_pin)
        self.pin_failed_attempts, self.pin_locked_until = 0, None
        self.save(update_fields=["transaction_pin", "pin_failed_attempts", "pin_locked_until", "updated_at"])

    def _check_pin(
        self, raw_pin, *, hashed, attempts_field, locked_field, max_attempts, lock_minutes, wrong, locked
    ):
        """Atomic attempt counting so concurrent guesses can't bypass the limit."""
        self.refresh_from_db(fields=[attempts_field, locked_field])
        locked_until = getattr(self, locked_field)
        if locked_until and locked_until > timezone.now():
            raise locked()
        if hashed and check_password(raw_pin, hashed):
            if getattr(self, attempts_field):
                type(self).objects.filter(pk=self.pk).update(**{attempts_field: 0, locked_field: None})
            return
        type(self).objects.filter(pk=self.pk).update(**{attempts_field: models.F(attempts_field) + 1})
        self.refresh_from_db(fields=[attempts_field])
        left = max_attempts - getattr(self, attempts_field)
        if left <= 0:
            until = timezone.now() + timedelta(minutes=lock_minutes)
            type(self).objects.filter(pk=self.pk).update(**{locked_field: until, attempts_field: 0})
            raise locked()
        exc = wrong()
        exc.extra_details = {"attempts_left": left}
        raise exc

    def verify_login_pin(self, raw_pin: str) -> None:
        self._check_pin(
            raw_pin,
            hashed=self.login_pin,
            attempts_field="login_pin_failed_attempts",
            locked_field="login_pin_locked_until",
            max_attempts=settings.LOGIN_PIN_MAX_ATTEMPTS,
            lock_minutes=settings.LOGIN_PIN_LOCKOUT_MINUTES,
            wrong=InvalidLoginPIN,
            locked=LoginPINLocked,
        )

    def verify_transaction_pin(self, raw_pin: str) -> None:
        if not self.has_transaction_pin:
            raise TransactionPINNotSet()
        self._check_pin(
            raw_pin,
            hashed=self.transaction_pin,
            attempts_field="pin_failed_attempts",
            locked_field="pin_locked_until",
            max_attempts=settings.TRANSACTION_PIN_MAX_ATTEMPTS,
            lock_minutes=settings.TRANSACTION_PIN_LOCKOUT_MINUTES,
            wrong=InvalidTransactionPIN,
            locked=TransactionPINLocked,
        )


class Device(TimeStampedModel):
    """A phone/browser proven by OTP. Only bound devices can log in with the PIN alone; the client holds
    device_id + a secret and we keep only the secret's hash."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="devices")
    device_id = models.CharField(max_length=64)
    secret_hash = models.CharField(max_length=128)
    name = models.CharField(max_length=100, blank=True)
    push_token = models.CharField(max_length=255, blank=True)
    last_login_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "device_id"], name="device_unique_per_user")]

    def __str__(self):
        return f"{self.user} · {self.name or self.device_id[:8]}"


class OTPChallenge(TimeStampedModel):
    """A one-time code sent by SMS or email. Only the code's HMAC is stored."""

    class Purpose(models.TextChoices):
        SIGNUP = "signup", _("Sign up")
        NEW_DEVICE = "new_device", _("New device")
        RESET_PIN = "reset_pin", _("Reset PIN")

    class Channel(models.TextChoices):
        SMS = "sms", "SMS"
        EMAIL = "email", _("Email")

    purpose = models.CharField(max_length=12, choices=Purpose.choices)
    channel = models.CharField(max_length=5, choices=Channel.choices)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    phone_number = models.CharField(max_length=16, blank=True)
    email = models.EmailField(blank=True)
    code_hash = models.CharField(max_length=64, blank=True)
    payload = models.JSONField(default=dict, blank=True, help_text=_("Pending sign-up details."))
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    sends = models.PositiveSmallIntegerField(default=0)
    last_sent_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.purpose} via {self.channel}"


class Consent(TimeStampedModel):
    """NDPA: what the user agreed to, which version, and when (withdrawal keeps the history)."""

    class Purpose(models.TextChoices):
        TERMS = "terms", _("Terms of service")
        PRIVACY = "privacy", _("Privacy policy")
        WHATSAPP = "whatsapp", _("WhatsApp messages")
        MARKETING = "marketing", _("Marketing")
        LOCATION = "location", _("Location for safety alerts")

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="consents")
    purpose = models.CharField(max_length=12, choices=Purpose.choices)
    version = models.CharField(max_length=20)
    granted_at = models.DateTimeField(default=timezone.now)
    withdrawn_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["user", "purpose"])]


class DataRequest(TimeStampedModel):
    """NDPA data-subject request: export or delete my data. Processed by staff (automated in Phase 6)."""

    class Kind(models.TextChoices):
        EXPORT = "export", _("Export my data")
        DELETE = "delete", _("Delete my account and data")

    class Status(models.TextChoices):
        RECEIVED = "received", _("Received")
        IN_PROGRESS = "in_progress", _("In progress")
        COMPLETED = "completed", _("Completed")
        REJECTED = "rejected", _("Rejected (legal retention)")

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="data_requests")
    kind = models.CharField(max_length=6, choices=Kind.choices)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.RECEIVED)
    note = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
