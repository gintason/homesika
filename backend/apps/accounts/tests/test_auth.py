"""Phone-first sign-up with a one-time code, a 6-digit login PIN, PIN-only login on trusted devices."""

import re

import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Consent, Device, OTPChallenge, User
from conftest import LOGIN_PIN, make_user

pytestmark = pytest.mark.django_db
DEVICE = "dev_0123456789abcdef"
SIGNUP = {
    "first_name": "Chidi",
    "last_name": "Okafor",
    "phone_number": "0809 999 9999",  # local format is normalised to +2348099999999
    "email": "Chidi@Example.com",
    "accept_terms": True,
}


def code_in(text: str) -> str:
    return re.search(r"\b(\d{6})\b", text).group(1)


def post(client, name, body):
    return client.post(reverse(f"v1:{name}"), body, format="json")


def sign_up(client, outbox, pin="739152", device=DEVICE, **overrides):
    start = post(client, "register", {**SIGNUP, **overrides})
    assert start.status_code == 201, start.json()
    verify = post(
        client, "otp-verify", {"challenge_id": start.json()["challenge_id"], "code": code_in(outbox[-1][1])}
    )
    assert verify.status_code == 200, verify.json()
    setup = post(
        client,
        "pin-setup",
        {"setup_token": verify.json()["setup_token"], "pin": pin, "pin_confirm": pin, "device_id": device},
    )
    assert setup.status_code == 201, setup.json()
    return setup.json()


def test_sign_up_by_sms_then_pin(api_client, _sms_outbox):
    start = post(api_client, "register", SIGNUP).json()
    assert (start["channel"], start["destination"], start["email_fallback"]) == ("sms", "+234•••••999", True)
    assert not User.objects.exists()  # nothing created before the code
    assert _sms_outbox[0][0] == "+2348099999999" and "Homesika" in _sms_outbox[0][1]

    bad = post(api_client, "otp-verify", {"challenge_id": start["challenge_id"], "code": "000000"})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "otp_invalid"

    verify = post(
        api_client, "otp-verify", {"challenge_id": start["challenge_id"], "code": code_in(_sms_outbox[0][1])}
    )
    user = User.objects.get(phone_number="+2348099999999")
    assert (user.email, user.is_phone_verified, user.has_usable_password()) == (
        "chidi@example.com",
        True,
        False,
    )
    assert set(Consent.objects.filter(user=user).values_list("purpose", flat=True)) == {"terms", "privacy"}

    token = verify.json()["setup_token"]
    weak = post(
        api_client,
        "pin-setup",
        {"setup_token": token, "pin": "123456", "pin_confirm": "123456", "device_id": DEVICE},
    )
    assert weak.status_code == 400 and "pin" in weak.json()["error"]["details"]
    done = post(
        api_client,
        "pin-setup",
        {"setup_token": token, "pin": "739152", "pin_confirm": "739152", "device_id": DEVICE},
    )
    data = done.json()
    assert done.status_code == 201 and data["user"]["has_login_pin"] and data["device_secret"]
    assert data["device_secret"] not in Device.objects.get(user=user).secret_hash  # only a hash is stored
    reused = post(
        api_client,
        "pin-setup",
        {"setup_token": token, "pin": "739152", "pin_confirm": "739152", "device_id": DEVICE},
    )
    assert reused.status_code == 401 and reused.json()["error"]["code"] == "setup_expired"


def test_email_is_optional_and_terms_are_required(api_client, _sms_outbox):
    no_terms = post(api_client, "register", {**SIGNUP, "accept_terms": False})
    assert no_terms.status_code == 400 and "accept_terms" in no_terms.json()["error"]["details"]
    no_email_but_email_channel = post(api_client, "register", {**SIGNUP, "email": "", "channel": "email"})
    assert "email" in no_email_but_email_channel.json()["error"]["details"]
    sign_up(api_client, _sms_outbox, email="")
    assert User.objects.get().email is None


def test_email_fallback(api_client, _sms_outbox):
    cid = post(api_client, "register", SIGNUP).json()["challenge_id"]
    OTPChallenge.objects.filter(pk=cid).update(last_sent_at=timezone.now() - timezone.timedelta(minutes=2))
    resent = post(api_client, "otp-resend", {"challenge_id": cid, "channel": "email"}).json()
    assert (resent["channel"], resent["destination"]) == ("email", "ch•••@example.com")
    post(api_client, "otp-verify", {"challenge_id": cid, "code": code_in(mail.outbox[-1].body)})
    user = User.objects.get()
    assert (user.is_email_verified, user.is_phone_verified) == (True, False)


def test_code_attempts_and_resend_are_limited(api_client, _sms_outbox):
    cid = post(api_client, "register", SIGNUP).json()["challenge_id"]
    assert post(api_client, "otp-resend", {"challenge_id": cid}).status_code == 429
    codes = [
        post(api_client, "otp-verify", {"challenge_id": cid, "code": "000000"}).status_code for _ in range(5)
    ]
    assert codes[-1] == 429
    assert (
        post(api_client, "otp-verify", {"challenge_id": cid, "code": code_in(_sms_outbox[0][1])}).status_code
        == 429
    )


def test_duplicate_phone_is_rejected_before_any_sms(api_client, user, _sms_outbox):
    resp = post(api_client, "register", {**SIGNUP, "phone_number": user.phone_number})
    assert resp.status_code == 400 and "phone_number" in resp.json()["error"]["details"]
    assert _sms_outbox == []


def test_pin_only_login_and_lockout(api_client, _sms_outbox):
    secret = sign_up(api_client, _sms_outbox)["device_secret"]
    ok = post(api_client, "pin-login", {"device_id": DEVICE, "device_secret": secret, "pin": "739152"})
    assert ok.status_code == 200 and ok.json()["user"]["first_name"] == "Chidi"
    wrong = post(api_client, "pin-login", {"device_id": DEVICE, "device_secret": secret, "pin": "111222"})
    assert wrong.status_code == 403 and wrong.json()["error"]["details"] == {"attempts_left": 4}
    codes = [
        post(
            api_client, "pin-login", {"device_id": DEVICE, "device_secret": secret, "pin": "111222"}
        ).status_code
        for _ in range(4)
    ]
    assert codes[-1] == 423
    stranger = post(api_client, "pin-login", {"device_id": DEVICE, "device_secret": "guess", "pin": "739152"})
    assert stranger.status_code == 401 and stranger.json()["error"]["code"] == "device_not_recognised"


def test_new_device_needs_pin_and_code(api_client, user, _sms_outbox):
    assert post(api_client, "login", {"identifier": "08012345678", "pin": "000111"}).status_code == 403
    assert post(api_client, "login", {"identifier": "ghost@x.com", "pin": LOGIN_PIN}).status_code == 403
    assert _sms_outbox == []
    start = post(api_client, "login", {"identifier": "08012345678", "pin": LOGIN_PIN}).json()
    done = post(
        api_client,
        "otp-verify",
        {
            "challenge_id": start["challenge_id"],
            "code": code_in(_sms_outbox[-1][1]),
            "device_id": "new_phone_000000001",
        },
    ).json()
    assert (
        done["next"] == "done" and Device.objects.filter(user=user, device_id="new_phone_000000001").exists()
    )


def test_forgot_pin_signs_out_other_devices(api_client, _sms_outbox):
    old_secret = sign_up(api_client, _sms_outbox)["device_secret"]
    decoy = post(api_client, "pin-forgot", {"identifier": "+2348000000000"})
    assert decoy.status_code == 201 and len(_sms_outbox) == 1  # unknown account: same answer, nothing sent
    start = post(api_client, "pin-forgot", {"identifier": "+2348099999999"}).json()
    verify = post(
        api_client, "otp-verify", {"challenge_id": start["challenge_id"], "code": code_in(_sms_outbox[-1][1])}
    )
    new = post(
        api_client,
        "pin-setup",
        {
            "setup_token": verify.json()["setup_token"],
            "pin": "592846",
            "pin_confirm": "592846",
            "device_id": "replacement_dev_001",
        },
    )
    assert new.status_code == 200
    old = post(api_client, "pin-login", {"device_id": DEVICE, "device_secret": old_secret, "pin": "592846"})
    assert old.status_code == 401


def test_logout_forgets_device_and_blacklists_refresh(api_client, _sms_outbox):
    data = sign_up(api_client, _sms_outbox)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {data['tokens']['access']}")
    assert (
        post(api_client, "logout", {"refresh": data["tokens"]["refresh"], "device_id": DEVICE}).status_code
        == 204
    )
    api_client.credentials()
    again = post(
        api_client,
        "pin-login",
        {"device_id": DEVICE, "device_secret": data["device_secret"], "pin": "739152"},
    )
    assert again.status_code == 401
    assert post(api_client, "token-refresh", {"refresh": data["tokens"]["refresh"]}).status_code == 401


def test_transaction_pin_needs_login_pin(auth_client, user):
    url = reverse("v1:transaction-pin")
    bad = auth_client.post(url, {"login_pin": "000000", "pin": "4826", "pin_confirm": "4826"}, format="json")
    assert bad.status_code == 403
    ok = auth_client.post(url, {"login_pin": LOGIN_PIN, "pin": "4826", "pin_confirm": "4826"}, format="json")
    assert ok.status_code == 204
    user.refresh_from_db()
    user.verify_transaction_pin("4826")
    assert (
        auth_client.post(
            url, {"login_pin": LOGIN_PIN, "pin": "1234", "pin_confirm": "1234"}, format="json"
        ).status_code
        == 400
    )


def test_me_cannot_change_protected_fields(auth_client, user):
    resp = auth_client.patch(
        reverse("v1:me"), {"preferred_language": "pcm", "phone_number": "+2340000000000"}, format="json"
    )
    assert resp.status_code == 200
    user.refresh_from_db()
    assert (user.preferred_language, user.phone_number) == ("pcm", "+2348012345678")


def test_consents_and_data_requests(auth_client, user):
    auth_client.post(reverse("v1:consents"), {"purpose": "location", "version": "2026-10"}, format="json")
    assert auth_client.post(reverse("v1:consent-withdraw", args=["location"])).status_code == 204
    assert Consent.objects.get(user=user, purpose="location").withdrawn_at is not None
    assert auth_client.post(reverse("v1:consent-withdraw", args=["terms"])).status_code == 400
    resp = auth_client.post(reverse("v1:data-requests"), {"kind": "export"}, format="json")
    assert resp.status_code == 201 and resp.json()["status"] == "received"


def test_shared_phone_logs_each_account_into_its_own(api_client, _sms_outbox):
    make_user(phone="+2348012345678")
    start = post(api_client, "login", {"identifier": "+2348012345678", "pin": LOGIN_PIN}).json()
    ada = post(
        api_client,
        "otp-verify",
        {"challenge_id": start["challenge_id"], "code": code_in(_sms_outbox[-1][1]), "device_id": DEVICE},
    ).json()
    chidi = sign_up(api_client, _sms_outbox)
    as_chidi = post(
        api_client,
        "pin-login",
        {"device_id": DEVICE, "device_secret": chidi["device_secret"], "pin": "739152"},
    )
    as_ada = post(
        api_client,
        "pin-login",
        {"device_id": DEVICE, "device_secret": ada["device_secret"], "pin": LOGIN_PIN},
    )
    assert (as_chidi.json()["user"]["first_name"], as_ada.json()["user"]["first_name"]) == ("Chidi", "Ada")


def test_new_device_login_is_rate_limited(api_client, user):
    codes = [
        post(api_client, "login", {"identifier": "x@y.com", "pin": "000111"}).status_code for _ in range(6)
    ]
    assert codes[:5] == [403] * 5 and codes[5] == 429
