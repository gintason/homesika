"""
One-time codes for sign-up, new-device login and PIN reset.

* 6 digits, valid OTP_TTL_MINUTES, at most OTP_MAX_ATTEMPTS guesses per code.
* Resend after OTP_RESEND_SECONDS, at most OTP_MAX_SENDS per challenge, and at most
  OTP_MAX_PER_HOUR codes per phone/email per hour (stops SMS-cost abuse).
* Only an HMAC of the code is stored. SMS can fall back to email on request.
"""

import hashlib
import hmac
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _lazy
from rest_framework import status

from apps.core.exceptions import HomesikaAPIException
from apps.notifications import sms

from .models import OTPChallenge

logger = logging.getLogger(__name__)
Channel, Purpose = OTPChallenge.Channel, OTPChallenge.Purpose
SETUP_SALT = "homesika.pin-setup"


class OTPInvalid(HomesikaAPIException):
    default_detail = _lazy("That code is incorrect or has expired.")
    default_code = "otp_invalid"


class OTPTooManyAttempts(HomesikaAPIException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_detail = _lazy("Too many incorrect codes. Request a new one.")
    default_code = "otp_attempts_exceeded"


class OTPResendLimited(HomesikaAPIException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_detail = _lazy("Please wait before requesting another code.")
    default_code = "otp_resend_limited"


class OTPDeliveryFailed(HomesikaAPIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = _lazy(
        "We couldn't send the code right now. Try again, or send it to your email instead."
    )
    default_code = "otp_delivery_failed"


class SetupTokenInvalid(HomesikaAPIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = _lazy("This step has expired. Please start again.")
    default_code = "setup_expired"


def _hash(challenge_id, code: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode(), f"{challenge_id}:{code}".encode(), hashlib.sha256
    ).hexdigest()


def mask(channel: str, phone: str = "", email: str = "") -> str:
    if channel == Channel.SMS:
        return f"{phone[:4]}•••••{phone[-3:]}" if phone else ""
    local, _sep, domain = email.partition("@")
    return f"{local[:2]}•••@{domain}" if email else ""


def describe(ch: OTPChallenge) -> dict:
    wait = 0
    if ch.last_sent_at:
        wait = max(0, settings.OTP_RESEND_SECONDS - int((timezone.now() - ch.last_sent_at).total_seconds()))
    return {
        "challenge_id": str(ch.pk),
        "purpose": ch.purpose,
        "channel": ch.channel,
        "destination": mask(ch.channel, ch.phone_number, ch.email),
        "email_fallback": bool(ch.email) and ch.channel == Channel.SMS,
        "expires_in": max(0, int((ch.expires_at - timezone.now()).total_seconds())),
        "resend_in": wait,
    }


def create(
    purpose, *, phone="", email="", user=None, payload=None, channel=Channel.SMS, send=True
) -> OTPChallenge:
    if channel == Channel.SMS and not phone:
        channel = Channel.EMAIL
    ch = OTPChallenge.objects.create(
        purpose=purpose,
        channel=channel,
        user=user,
        phone_number=phone or "",
        email=email or "",
        payload=payload or {},
        expires_at=timezone.now() + timedelta(minutes=settings.OTP_TTL_MINUTES),
    )
    if send:
        deliver(ch)
    return ch


def deliver(ch: OTPChallenge, channel: str | None = None) -> OTPChallenge:
    if channel and channel != ch.channel:
        if channel == Channel.EMAIL and not ch.email or channel == Channel.SMS and not ch.phone_number:
            raise OTPInvalid()
        ch.channel = channel
    if ch.verified_at:
        raise OTPInvalid()
    if ch.last_sent_at and describe(ch)["resend_in"] > 0 or ch.sends >= settings.OTP_MAX_SENDS:
        raise OTPResendLimited()
    destination = ch.phone_number if ch.channel == Channel.SMS else ch.email
    rate_key = "otp:dest:" + hashlib.sha256(destination.lower().encode()).hexdigest()
    cache.add(rate_key, 0, timeout=3600)
    if cache.incr(rate_key) > settings.OTP_MAX_PER_HOUR:
        raise OTPResendLimited()

    code = f"{secrets.randbelow(10**6):06d}"
    text = _(
        "Your Homesika code is %(code)s. It expires in %(minutes)s minutes. Never share it with anyone."
    ) % {
        "code": code,
        "minutes": settings.OTP_TTL_MINUTES,
    }
    try:
        if ch.channel == Channel.SMS:
            sms.send_sms(ch.phone_number, text)
        else:
            send_mail(
                _("Your Homesika code"), text, settings.DEFAULT_FROM_EMAIL, [ch.email], fail_silently=False
            )
    except (sms.SmsError, OSError) as exc:
        logger.warning("OTP delivery via %s failed: %s", ch.channel, exc)
        raise OTPDeliveryFailed() from exc

    ch.code_hash = _hash(ch.pk, code)
    ch.attempts = 0
    ch.sends += 1
    ch.last_sent_at = timezone.now()
    ch.expires_at = timezone.now() + timedelta(minutes=settings.OTP_TTL_MINUTES)
    ch.save(
        update_fields=[
            "channel",
            "code_hash",
            "attempts",
            "sends",
            "last_sent_at",
            "expires_at",
            "updated_at",
        ]
    )
    return ch


def get(challenge_id) -> OTPChallenge:
    try:
        return OTPChallenge.objects.get(pk=challenge_id)
    except (OTPChallenge.DoesNotExist, ValueError, DjangoValidationError) as exc:  # unknown or malformed id
        raise OTPInvalid() from exc


def verify(challenge_id, code: str) -> OTPChallenge:
    ch = get(challenge_id)
    if ch.verified_at or not ch.code_hash or ch.expires_at <= timezone.now():
        raise OTPInvalid()
    if ch.attempts >= settings.OTP_MAX_ATTEMPTS:
        raise OTPTooManyAttempts()
    OTPChallenge.objects.filter(pk=ch.pk).update(attempts=ch.attempts + 1)
    if not hmac.compare_digest(ch.code_hash, _hash(ch.pk, code.strip())):
        if ch.attempts + 1 >= settings.OTP_MAX_ATTEMPTS:
            raise OTPTooManyAttempts()
        raise OTPInvalid()
    ch.verified_at = timezone.now()
    ch.save(update_fields=["verified_at", "updated_at"])
    return ch


# ---- Short-lived token between "code verified" and "PIN created" ---------------------------


def setup_token(user, ch: OTPChallenge) -> str:
    return signing.dumps({"u": str(user.pk), "c": str(ch.pk), "p": ch.purpose}, salt=SETUP_SALT)


def read_setup_token(token: str) -> tuple[str, OTPChallenge]:
    """Returns (user_id, challenge). Single use: the challenge is marked used."""
    try:
        data = signing.loads(token, salt=SETUP_SALT, max_age=settings.PIN_SETUP_TOKEN_SECONDS)
    except signing.BadSignature as exc:
        raise SetupTokenInvalid() from exc
    ch = OTPChallenge.objects.filter(pk=data["c"], verified_at__isnull=False).first()
    if ch is None or ch.payload.get("setup_used"):
        raise SetupTokenInvalid()
    return data["u"], ch


def mark_setup_used(ch: OTPChallenge) -> None:
    ch.payload = {**ch.payload, "setup_used": True}
    ch.save(update_fields=["payload", "updated_at"])
