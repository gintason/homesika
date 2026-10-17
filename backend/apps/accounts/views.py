"""
Authentication: phone (or email) + one-time code to verify, a 6-digit login PIN instead of a password.

    sign up      register -> otp/verify -> pin/setup                 (device bound, signed in)
    relaunch     pin-login (device_id + device_secret + PIN)         (PIN only)
    new device   login (phone/email + PIN) -> otp/verify             (device bound, signed in)
    forgot PIN   pin/forgot -> otp/verify -> pin/setup               (all other devices signed out)
"""

import hashlib
import secrets

from django.contrib.auth.hashers import make_password
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from apps.core import audit

from . import otp
from .exceptions import DeviceNotRecognised, InvalidLoginPIN
from .models import Consent, DataRequest, Device, OTPChallenge, User
from .serializers import (
    ChangeLoginPINSerializer,
    ConsentSerializer,
    DataRequestSerializer,
    ForgotPinSerializer,
    LoginStartSerializer,
    LogoutSerializer,
    OTPSerializer,
    PinLoginSerializer,
    PinSetupSerializer,
    RegisterSerializer,
    TransactionPINSerializer,
    UserSerializer,
    VerifySerializer,
)
from .signals import user_registered
from .throttles import AuthRateThrottle, OTPRateThrottle, PinLoginRateThrottle, PINRateThrottle
from .validators import normalise_phone

Purpose = OTPChallenge.Purpose
TERMS_VERSION = "2026-10"


def _tokens_for(user):
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


def _secret_hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _signed_in(user, device_id: str, device_name: str, *, http_status=status.HTTP_200_OK):
    """Trust this device for PIN-only login; the client stores the secret, we keep its hash."""
    secret = secrets.token_urlsafe(32)
    Device.objects.update_or_create(
        user=user,
        device_id=device_id,
        defaults={
            "secret_hash": _secret_hash(secret),
            "name": device_name[:100],
            "revoked_at": None,
            "last_login_at": timezone.now(),
        },
    )
    User.objects.filter(pk=user.pk).update(last_login=timezone.now())
    return Response(
        {
            "next": "done",
            "user": UserSerializer(user).data,
            "tokens": _tokens_for(user),
            "device_secret": secret,
        },
        status=http_status,
    )


def _sign_out_everywhere(user) -> None:
    Device.objects.filter(user=user, revoked_at__isnull=True).update(revoked_at=timezone.now())
    for token in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=token)


def _find_user(identifier: str) -> User | None:
    identifier = identifier.strip()
    if "@" in identifier:
        return User.objects.filter(is_active=True, email__iexact=identifier).first()
    return User.objects.filter(is_active=True, phone_number=normalise_phone(identifier)).first()


class RegisterView(generics.GenericAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [OTPRateThrottle]

    @extend_schema(responses={201: OpenApiTypes.OBJECT})
    def post(self, request):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = dict(s.validated_data)
        channel = data.pop("channel")
        data.pop("accept_terms")
        ch = otp.create(
            Purpose.SIGNUP,
            phone=data["phone_number"],
            email=data.get("email") or "",
            payload={**data, "terms_version": TERMS_VERSION},
            channel=channel,
        )
        return Response(otp.describe(ch), status=status.HTTP_201_CREATED)


class OTPResendView(generics.GenericAPIView):
    serializer_class = OTPSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [OTPRateThrottle]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def post(self, request):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        ch = otp.get(s.validated_data["challenge_id"])
        if ch.payload.get("decoy"):
            return Response(otp.describe(ch))
        return Response(otp.describe(otp.deliver(ch, s.validated_data.get("channel"))))


class OTPVerifyView(generics.GenericAPIView):
    serializer_class = VerifySerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [OTPRateThrottle]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def post(self, request):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        ch = otp.verify(s.validated_data["challenge_id"], s.validated_data["code"])
        if ch.purpose == Purpose.SIGNUP:
            user = self._create_user(ch)
            return Response({"next": "create_pin", "setup_token": otp.setup_token(user, ch)})
        if ch.purpose == Purpose.RESET_PIN:
            return Response({"next": "create_pin", "setup_token": otp.setup_token(ch.user, ch)})
        if not s.validated_data.get("device_id"):
            raise serializers.ValidationError({"device_id": [_("This field is required.")]})
        return _signed_in(ch.user, s.validated_data["device_id"], s.validated_data["device_name"])

    @staticmethod
    def _create_user(ch: OTPChallenge) -> User:
        data = {
            k: v for k, v in ch.payload.items() if k not in ("setup_used", "terms_version", "referral_code")
        }
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    password=None,
                    is_phone_verified=ch.channel == OTPChallenge.Channel.SMS,
                    is_email_verified=ch.channel == OTPChallenge.Channel.EMAIL,
                    **{**data, "email": data.get("email") or None},
                )
                version = ch.payload.get("terms_version", TERMS_VERSION)
                Consent.objects.bulk_create(
                    [
                        Consent(user=user, purpose=Consent.Purpose.TERMS, version=version),
                        Consent(user=user, purpose=Consent.Purpose.PRIVACY, version=version),
                    ]
                )
        except IntegrityError as exc:
            raise serializers.ValidationError(
                {"non_field_errors": [_("An account with these details already exists.")]}
            ) from exc
        user_registered.send(sender=User, user=user)
        if ch.payload.get("referral_code"):
            from apps.referrals import services as referrals

            try:
                referrals.attribute(user, ch.payload["referral_code"])
            except serializers.ValidationError:
                pass  # the code was checked at step 1; never block a sign-up over a reward
        return user


class PinSetupView(generics.GenericAPIView):
    serializer_class = PinSetupSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [OTPRateThrottle]

    @extend_schema(responses={200: OpenApiTypes.OBJECT, 201: OpenApiTypes.OBJECT})
    def post(self, request):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        user_id, ch = otp.read_setup_token(s.validated_data["setup_token"])
        user = User.objects.get(pk=user_id, is_active=True)
        with transaction.atomic():
            otp.mark_setup_used(ch)
            if ch.purpose == Purpose.RESET_PIN:
                _sign_out_everywhere(user)
                audit.record("auth.pin_reset", actor=user, obj=user, request=request)
            user.set_login_pin(s.validated_data["pin"])
        return _signed_in(
            user,
            s.validated_data["device_id"],
            s.validated_data["device_name"],
            http_status=status.HTTP_201_CREATED if ch.purpose == Purpose.SIGNUP else status.HTTP_200_OK,
        )


class PinLoginView(generics.GenericAPIView):
    """Everyday login on a trusted device: PIN only."""

    serializer_class = PinLoginSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [PinLoginRateThrottle]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def post(self, request):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        # Match on the secret too: one phone can be linked to more than one account over time.
        device = (
            Device.objects.select_related("user")
            .filter(
                device_id=s.validated_data["device_id"],
                secret_hash=_secret_hash(s.validated_data["device_secret"]),
                revoked_at__isnull=True,
                user__is_active=True,
            )
            .first()
        )
        if device is None:
            raise DeviceNotRecognised()
        device.user.verify_login_pin(s.validated_data["pin"])
        now = timezone.now()
        Device.objects.filter(pk=device.pk).update(last_login_at=now)
        User.objects.filter(pk=device.user_id).update(last_login=now)
        return Response({"user": UserSerializer(device.user).data, "tokens": _tokens_for(device.user)})


class LoginStartView(generics.GenericAPIView):
    """New or reinstalled device: phone/email + PIN, then a code to prove it's really you."""

    serializer_class = LoginStartSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AuthRateThrottle]

    @extend_schema(responses={201: OpenApiTypes.OBJECT})
    def post(self, request):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = _find_user(s.validated_data["identifier"])
        if user is None or not user.has_login_pin:
            make_password(s.validated_data["pin"])  # same work as a real check: no account probing by timing
            raise InvalidLoginPIN()
        user.verify_login_pin(s.validated_data["pin"])
        ch = otp.create(Purpose.NEW_DEVICE, phone=user.phone_number, email=user.email or "", user=user)
        return Response(otp.describe(ch), status=status.HTTP_201_CREATED)


class ForgotPinView(generics.GenericAPIView):
    serializer_class = ForgotPinSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [OTPRateThrottle]

    @extend_schema(responses={201: OpenApiTypes.OBJECT})
    def post(self, request):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        identifier = s.validated_data["identifier"].strip()
        user = _find_user(identifier)
        if user is None:
            # Same response shape, nothing sent: doesn't reveal whether the account exists.
            is_email = "@" in identifier
            ch = otp.create(
                Purpose.RESET_PIN,
                phone="" if is_email else normalise_phone(identifier),
                email=identifier if is_email else "",
                payload={"decoy": True},
                send=False,
            )
            ch.last_sent_at = timezone.now()
            return Response(otp.describe(ch), status=status.HTTP_201_CREATED)
        ch = otp.create(Purpose.RESET_PIN, phone=user.phone_number, email=user.email or "", user=user)
        return Response(otp.describe(ch), status=status.HTTP_201_CREATED)


class RefreshView(TokenRefreshView):
    throttle_classes = [AuthRateThrottle]


class LogoutView(generics.GenericAPIView):
    """Sign this device out: blacklist the refresh token and forget the device."""

    serializer_class = LogoutSerializer

    @extend_schema(responses={204: None})
    def post(self, request):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            token = RefreshToken(s.validated_data["refresh"])
            if str(token["user_id"]) == str(request.user.pk):
                token.blacklist()
        except TokenError:
            pass  # already invalid: logging out is idempotent
        if s.validated_data.get("device_id"):
            Device.objects.filter(user=request.user, device_id=s.validated_data["device_id"]).update(
                revoked_at=timezone.now()
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    http_method_names = ["get", "patch"]

    def get_object(self):
        return self.request.user


class ChangeLoginPINView(generics.GenericAPIView):
    serializer_class = ChangeLoginPINSerializer
    throttle_classes = [PINRateThrottle]

    @extend_schema(responses={204: None})
    def post(self, request):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        request.user.verify_login_pin(s.validated_data["current_pin"])
        request.user.set_login_pin(s.validated_data["pin"])
        audit.record("auth.login_pin_changed", actor=request.user, obj=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TransactionPINView(generics.GenericAPIView):
    serializer_class = TransactionPINSerializer
    throttle_classes = [PINRateThrottle]

    @extend_schema(responses={204: None})
    def post(self, request):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        request.user.set_transaction_pin(s.validated_data["pin"])
        audit.record("auth.transaction_pin_set", actor=request.user, obj=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ConsentListView(generics.ListCreateAPIView):
    """NDPA: list my consents; POST grants one (e.g. location for safety alerts)."""

    serializer_class = ConsentSerializer
    pagination_class = None

    def get_queryset(self):
        return Consent.objects.filter(user=self.request.user).order_by("-granted_at")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class ConsentWithdrawView(generics.GenericAPIView):
    @extend_schema(request=None, responses={204: None})
    def post(self, request, purpose):
        if purpose in (Consent.Purpose.TERMS, Consent.Purpose.PRIVACY):
            raise serializers.ValidationError(
                {"purpose": [_("To withdraw this consent, request account deletion instead.")]}
            )
        Consent.objects.filter(user=request.user, purpose=purpose, withdrawn_at__isnull=True).update(
            withdrawn_at=timezone.now()
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class DataRequestView(generics.ListCreateAPIView):
    """NDPA: ask for a copy of my data, or for my account and data to be deleted."""

    serializer_class = DataRequestSerializer
    pagination_class = None

    def get_queryset(self):
        return DataRequest.objects.filter(user=self.request.user).order_by("-created_at")

    def perform_create(self, serializer):
        obj = serializer.save(user=self.request.user)
        audit.record(f"privacy.{obj.kind}_requested", actor=self.request.user, obj=obj, request=self.request)
