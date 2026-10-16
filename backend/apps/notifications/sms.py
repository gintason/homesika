"""
SMS behind one interface. SMS_PROVIDER picks the adapter:

* "mock": MOCK, writes the message to the log (and an in-memory outbox in tests); sends nothing.
* "termii": Termii (Nigeria). Real adapter; fields marked TODO(verify) must be checked against
  Termii's current docs before going live.
"""

import logging
from typing import Protocol

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class SmsError(Exception):
    """The provider rejected or couldn't take the message."""


class SmsProvider(Protocol):
    name: str

    def send(self, phone_e164: str, text: str) -> str:
        """Send one message; return the provider's message id (or '' if none)."""


class MockSms:
    """MOCK adapter: nothing leaves the server. Used by default in local/dev and in tests."""

    name = "mock"
    outbox: list[tuple[str, str]] = []

    def send(self, phone_e164: str, text: str) -> str:
        MockSms.outbox.append((phone_e164, text))
        logger.warning("MOCK SMS (not sent) to %s: %s", phone_e164, text)
        return f"mock-{len(MockSms.outbox)}"


class TermiiSms:
    name = "termii"

    def send(self, phone_e164: str, text: str) -> str:
        # TODO(verify): endpoint path, field names and the "dnd" channel against Termii's current API docs.
        try:
            resp = requests.post(
                f"{settings.TERMII_BASE_URL.rstrip('/')}/api/sms/send",
                json={
                    "api_key": settings.TERMII_API_KEY,
                    "to": phone_e164.lstrip("+"),
                    "from": settings.TERMII_SENDER_ID,
                    "sms": text,
                    "type": "plain",
                    "channel": settings.TERMII_CHANNEL,
                },
                timeout=(5, 15),
            )
        except requests.RequestException as exc:
            raise SmsError(f"termii unreachable: {type(exc).__name__}") from exc
        if resp.status_code >= 400:
            raise SmsError(f"termii HTTP {resp.status_code}")
        try:
            return str(resp.json().get("message_id", ""))  # TODO(verify) response field
        except ValueError:
            return ""


_PROVIDERS = {"mock": MockSms, "termii": TermiiSms}


def provider() -> SmsProvider:
    return _PROVIDERS[settings.SMS_PROVIDER]()


def send_sms(phone_e164: str, text: str) -> str:
    return provider().send(phone_e164, text)
