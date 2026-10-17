"""
WhatsApp behind one interface. WHATSAPP_PROVIDER picks the adapter:

* "mock": MOCK. Nothing leaves the server; messages go to the log and an in-memory outbox (tests).
* "cloud": Meta's WhatsApp Cloud API (Graph API).

Meta's documentation could not be reached from the build environment, so everything below that
comes from memory of the Cloud API is marked TODO(verify) and must be checked against the current
docs before going live:
* the send endpoint POST {graph}/{version}/{phone_number_id}/messages and its body shapes
  (`messaging_product`, `type: text|template`, `template.components[].parameters`);
* the webhook: GET verification with hub.mode / hub.verify_token / hub.challenge, and the
  X-Hub-Signature-256 header = "sha256=" + HMAC-SHA256(app secret, raw body);
* inbound payload paths entry[].changes[].value.{messages, contacts, statuses};
* the 24-hour customer-service window (free-form text only within 24h of the person's last message;
  templates outside it).
"""

import hashlib
import hmac
import logging
from dataclasses import dataclass, field
from typing import Protocol

import requests
from django.conf import settings

logger = logging.getLogger(__name__)
TIMEOUT = (5, 20)


class WhatsAppError(Exception):
    def __init__(self, message: str, *, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


@dataclass
class InboundMessage:
    provider_message_id: str
    wa_id: str
    profile_name: str
    kind: str  # text | interactive | button | image | audio | ... (non-text kinds are stored, not answered)
    body: str
    timestamp: str = ""


@dataclass
class StatusUpdate:
    provider_message_id: str
    status: str  # sent | delivered | read | failed
    error: str = ""


@dataclass
class WebhookBatch:
    messages: list[InboundMessage] = field(default_factory=list)
    statuses: list[StatusUpdate] = field(default_factory=list)


class WhatsAppProvider(Protocol):
    name: str

    def send_text(self, wa_id: str, body: str) -> str: ...

    def send_template(self, wa_id: str, name: str, language: str, params: list[str]) -> str: ...

    def verify_signature(self, raw_body: bytes, headers) -> bool: ...


def parse_webhook(payload: dict) -> WebhookBatch:
    """Cloud API webhook body -> our types. TODO(verify) the paths against Meta's payload reference."""
    batch = WebhookBatch()
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            names = {
                c.get("wa_id"): ((c.get("profile") or {}).get("name") or "")
                for c in value.get("contacts") or []
            }
            for m in value.get("messages") or []:
                kind = m.get("type") or "unknown"
                if kind == "text":
                    body = (m.get("text") or {}).get("body", "")
                elif kind == "interactive":
                    inter = m.get("interactive") or {}
                    reply = inter.get("button_reply") or inter.get("list_reply") or {}
                    body = reply.get("title") or reply.get("id") or ""
                elif kind == "button":
                    body = (m.get("button") or {}).get("text", "")
                else:
                    body = ""
                batch.messages.append(
                    InboundMessage(
                        provider_message_id=m.get("id", ""),
                        wa_id=str(m.get("from", "")),
                        profile_name=names.get(m.get("from"), ""),
                        kind=kind,
                        body=body,
                        timestamp=str(m.get("timestamp", "")),
                    )
                )
            for s in value.get("statuses") or []:
                errors = s.get("errors") or []
                batch.statuses.append(
                    StatusUpdate(
                        provider_message_id=s.get("id", ""),
                        status=s.get("status", ""),
                        error=(errors[0].get("title") or str(errors[0].get("code", ""))) if errors else "",
                    )
                )
    return batch


class MockWhatsApp:
    """MOCK adapter for development and tests. Clearly not a real send."""

    name = "mock"
    outbox: list[dict] = []
    SECRET = b"mock-whatsapp-app-secret-not-a-secret"

    def send_text(self, wa_id: str, body: str) -> str:
        MockWhatsApp.outbox.append({"to": wa_id, "type": "text", "body": body})
        logger.warning("MOCK WhatsApp (not sent) to %s: %s", wa_id, body[:200])
        return f"wamid.MOCK{len(MockWhatsApp.outbox)}"

    def send_template(self, wa_id: str, name: str, language: str, params: list[str]) -> str:
        MockWhatsApp.outbox.append(
            {"to": wa_id, "type": "template", "name": name, "language": language, "params": params}
        )
        logger.warning("MOCK WhatsApp template %s (not sent) to %s", name, wa_id)
        return f"wamid.MOCK{len(MockWhatsApp.outbox)}"

    def verify_signature(self, raw_body: bytes, headers) -> bool:
        expected = "sha256=" + hmac.new(self.SECRET, raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(headers.get("x-hub-signature-256", ""), expected)


class CloudWhatsApp:
    name = "cloud"

    def __init__(self):
        version = settings.WHATSAPP_API_VERSION  # TODO(verify) the current Graph API version
        base = settings.WHATSAPP_GRAPH_URL.rstrip("/")
        self.url = f"{base}/{version}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
        self.token = settings.WHATSAPP_ACCESS_TOKEN
        self.app_secret = settings.WHATSAPP_APP_SECRET

    def _post(self, body: dict) -> str:
        try:
            resp = requests.post(
                self.url,
                json={"messaging_product": "whatsapp", "recipient_type": "individual", **body},
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            raise WhatsAppError(f"whatsapp unreachable: {type(exc).__name__}") from exc
        if resp.status_code >= 400:
            # 4xx (bad number, outside window, unapproved template) won't succeed on retry.
            raise WhatsAppError(f"whatsapp HTTP {resp.status_code}", retryable=resp.status_code >= 500)
        try:
            return ((resp.json().get("messages") or [{}])[0]).get("id", "")  # TODO(verify)
        except ValueError:
            return ""

    def send_text(self, wa_id: str, body: str) -> str:
        return self._post({"to": wa_id, "type": "text", "text": {"preview_url": False, "body": body}})

    def send_template(self, wa_id: str, name: str, language: str, params: list[str]) -> str:
        components = (
            [{"type": "body", "parameters": [{"type": "text", "text": p} for p in params]}] if params else []
        )
        return self._post(
            {
                "to": wa_id,
                "type": "template",
                "template": {"name": name, "language": {"code": language}, "components": components},
            }
        )

    def verify_signature(self, raw_body: bytes, headers) -> bool:
        if not self.app_secret:
            return False
        expected = "sha256=" + hmac.new(self.app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(headers.get("x-hub-signature-256", ""), expected)


_PROVIDERS = {"mock": MockWhatsApp, "cloud": CloudWhatsApp}


def enabled() -> bool:
    return settings.WHATSAPP_PROVIDER in _PROVIDERS


def provider() -> WhatsAppProvider:
    return _PROVIDERS[settings.WHATSAPP_PROVIDER]()
