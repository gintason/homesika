from django.conf import settings
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from .models import Consent, DataRequest, OTPChallenge, User
from .validators import (
    is_weak_pin,
    login_pin_validator,
    normalise_phone,
    phone_validator,
    transaction_pin_validator,
)

PIN6 = r"^\d{6}$"


class PhoneField(serializers.CharField):
    """Accepts 0801…, 234801…, +234 801…; stores E.164."""

    def to_internal_value(self, data):
        value = normalise_phone(super().to_internal_value(data))
        phone_validator(value)
        return value


class UserSerializer(serializers.ModelSerializer):
    has_login_pin = serializers.BooleanField(read_only=True)
    has_transaction_pin = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "phone_number",
            "email",
            "first_name",
            "last_name",
            "country",
            "preferred_language",
            "is_phone_verified",
            "is_email_verified",
            "has_login_pin",
            "has_transaction_pin",
            "created_at",
        )
        read_only_fields = (
            "id",
            "phone_number",
            "email",
            "is_phone_verified",
            "is_email_verified",
            "has_login_pin",
            "has_transaction_pin",
            "created_at",
        )


class RegisterSerializer(serializers.Serializer):
    """Step 1 of sign-up. Nothing is created until the code is verified."""

    first_name = serializers.CharField(max_length=80)
    last_name = serializers.CharField(max_length=80)
    phone_number = PhoneField()
    email = serializers.EmailField(required=False, allow_blank=True)
    preferred_language = serializers.ChoiceField(choices=settings.LANGUAGES, default="en")
    channel = serializers.ChoiceField(choices=OTPChallenge.Channel.choices, default=OTPChallenge.Channel.SMS)
    accept_terms = serializers.BooleanField()

    def validate_phone_number(self, value):
        if User.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError(_("An account with this phone number already exists."))
        return value

    def validate_email(self, value):
        value = (value or "").strip().lower()
        if value and User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(_("An account with this email already exists."))
        return value

    def validate_accept_terms(self, value):
        if not value:
            raise serializers.ValidationError(_("Please accept the terms and privacy policy to continue."))
        return value

    def validate(self, attrs):
        if attrs["channel"] == OTPChallenge.Channel.EMAIL and not attrs.get("email"):
            raise serializers.ValidationError(
                {"email": [_("Add an email address to receive the code by email.")]}
            )
        return attrs


class OTPSerializer(serializers.Serializer):
    challenge_id = serializers.CharField()
    channel = serializers.ChoiceField(choices=OTPChallenge.Channel.choices, required=False)


class DeviceSerializer(serializers.Serializer):
    device_id = serializers.RegexField(r"^[A-Za-z0-9_-]{16,64}$")
    device_name = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")


class VerifySerializer(DeviceSerializer):
    challenge_id = serializers.CharField()
    code = serializers.RegexField(PIN6)
    device_id = serializers.RegexField(r"^[A-Za-z0-9_-]{16,64}$", required=False)


class NewLoginPINSerializer(serializers.Serializer):
    pin = serializers.CharField(write_only=True, validators=[login_pin_validator])
    pin_confirm = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs["pin"] != attrs["pin_confirm"]:
            raise serializers.ValidationError({"pin_confirm": [_("PINs do not match.")]})
        if is_weak_pin(attrs["pin"]):
            raise serializers.ValidationError({"pin": [_("Choose a less predictable PIN.")]})
        return attrs


class PinSetupSerializer(NewLoginPINSerializer, DeviceSerializer):
    setup_token = serializers.CharField()


class LoginStartSerializer(serializers.Serializer):
    identifier = serializers.CharField(help_text="Phone number or email")
    pin = serializers.RegexField(PIN6)


class PinLoginSerializer(serializers.Serializer):
    device_id = serializers.CharField(max_length=64)
    device_secret = serializers.CharField(max_length=128)
    pin = serializers.RegexField(PIN6)


class ForgotPinSerializer(serializers.Serializer):
    identifier = serializers.CharField()


class ChangeLoginPINSerializer(NewLoginPINSerializer):
    current_pin = serializers.RegexField(PIN6)


class TransactionPINSerializer(serializers.Serializer):
    """Setting or changing the transaction PIN needs the login PIN (step-up)."""

    login_pin = serializers.RegexField(PIN6, write_only=True)
    pin = serializers.CharField(write_only=True, validators=[transaction_pin_validator])
    pin_confirm = serializers.CharField(write_only=True)

    def validate_login_pin(self, value):
        self.context["request"].user.verify_login_pin(value)
        return value

    def validate(self, attrs):
        if attrs["pin"] != attrs["pin_confirm"]:
            raise serializers.ValidationError({"pin_confirm": [_("PINs do not match.")]})
        if is_weak_pin(attrs["pin"]):
            raise serializers.ValidationError({"pin": [_("Choose a less predictable PIN.")]})
        return attrs


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()
    device_id = serializers.CharField(max_length=64, required=False)


class ConsentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Consent
        fields = ("id", "purpose", "version", "granted_at", "withdrawn_at")
        read_only_fields = ("id", "granted_at", "withdrawn_at")


class DataRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataRequest
        fields = ("id", "kind", "status", "created_at", "completed_at")
        read_only_fields = ("id", "status", "created_at", "completed_at")
