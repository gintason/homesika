"""
Push notifications behind one interface. PUSH_PROVIDER picks the adapter:

* "expo": Expo's push service through Expo's official server SDK (`exponent_server_sdk`). The app
  registers an Expo push token (expo-notifications); Expo forwards to FCM (Android) and APNs (iOS).
  Optional EXPO_ACCESS_TOKEN enables "enhanced push security" in your Expo account.
* "mock": MOCK, records messages in memory (tests) and the log; sends nothing.

Two steps, as Expo works: `send()` returns a ticket per message (accepted or an error such as
DeviceNotRegistered); `receipts()` later says whether Expo handed it to FCM/APNs. Neither proves the
person saw it: the app reports that itself (alerts' "received" call).
"""

import logging
from dataclasses import dataclass, field

from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass
class Push:
    token: str
    title: str
    body: str
    data: dict = field(default_factory=dict)
    urgent: bool = False  # alerts: high priority, alert sound, the "alerts" Android channel


@dataclass
class Ticket:
    ok: bool
    id: str = ""
    error: str = ""  # e.g. DeviceNotRegistered


class PushError(Exception):
    """Expo couldn't be reached or refused the whole request."""


class MockPush:
    name = "mock"
    outbox: list = []
    receipts_map: dict = {}  # tests set ticket id -> "ok" / "error:Reason" / "pending" (no receipt yet)

    def send(self, pushes: list[Push]) -> list[Ticket]:
        tickets = []
        for p in pushes:
            MockPush.outbox.append(p)
            logger.warning("MOCK PUSH (not sent) to %s: %s", p.token[:20], p.title)
            if "Invalid" in p.token:
                tickets.append(Ticket(False, error="DeviceNotRegistered"))
            else:
                tickets.append(Ticket(True, id=f"mock-{len(MockPush.outbox)}"))
        return tickets

    def receipts(self, ticket_ids: list[str]) -> dict[str, Ticket]:
        out = {}
        for tid in ticket_ids:
            v = MockPush.receipts_map.get(tid, "ok")
            if v == "pending":
                continue
            out[tid] = Ticket(v == "ok", tid, "" if v == "ok" else v.split(":", 1)[-1])
        return out


def _sound(p: Push):
    """iOS Critical Alerts ring even on silent / Do Not Disturb, but only with Apple's entitlement.
    TODO(verify): Expo's sound object for critical alerts ({"critical": true, "name", "volume"}) against
    Expo's push docs once the entitlement is granted. Android ignores it (the "alerts" channel is loud)."""
    if p.urgent and settings.PUSH_IOS_CRITICAL_ALERTS:
        return {"critical": True, "name": "default", "volume": 1.0}
    return "default"


class ExpoPush:
    name = "expo"

    def __init__(self):
        import requests
        from exponent_server_sdk import PushClient

        session = requests.Session()
        session.headers.update(
            {
                "accept": "application/json",
                "accept-encoding": "gzip, deflate",
                "content-type": "application/json",
            }
        )
        if settings.EXPO_ACCESS_TOKEN:
            session.headers.update({"Authorization": f"Bearer {settings.EXPO_ACCESS_TOKEN}"})
        self.client = PushClient(session=session, timeout=10)

    def send(self, pushes: list[Push]) -> list[Ticket]:
        from exponent_server_sdk import PushMessage, PushServerError
        from requests.exceptions import RequestException

        messages = [
            PushMessage(
                to=p.token,
                title=p.title,
                body=p.body,
                data=p.data,
                sound=_sound(p),
                priority="high" if p.urgent else "default",
                channel_id="alerts" if p.urgent else "default",
                ttl=60 * 10 if p.urgent else 60 * 60 * 24,
            )
            for p in pushes
        ]
        try:
            tickets = self.client.publish_multiple(messages)
        except (PushServerError, RequestException, ValueError) as exc:
            raise PushError(str(exc)[:200]) from exc
        out = []
        for t in tickets:
            if t.is_success():
                out.append(Ticket(True, id=t.id or ""))
            else:
                out.append(Ticket(False, error=str((t.details or {}).get("error") or t.message or "error")))
        return out

    def receipts(self, ticket_ids: list[str]) -> dict[str, Ticket]:
        from exponent_server_sdk import PushServerError, PushTicket
        from requests.exceptions import RequestException

        stubs = [
            PushTicket(push_message=None, status="ok", message="", details=None, id=i) for i in ticket_ids
        ]
        try:
            receipts = self.client.check_receipts_multiple(stubs)
        except (PushServerError, RequestException, ValueError) as exc:
            raise PushError(str(exc)[:200]) from exc
        return {
            r.id: Ticket(
                r.is_success(),
                r.id,
                "" if r.is_success() else str((r.details or {}).get("error") or r.message),
            )
            for r in receipts
        }


_PROVIDERS = {"mock": MockPush, "expo": ExpoPush}


def provider():
    return _PROVIDERS[settings.PUSH_PROVIDER]()


def active_tokens(user_ids) -> dict:
    """user id -> [tokens] for users with at least one active device."""
    from .models import PushDevice

    out: dict = {}
    for uid, token in PushDevice.objects.filter(user_id__in=list(user_ids), is_active=True).values_list(
        "user_id", "token"
    ):
        out.setdefault(uid, []).append(token)
    return out


def deactivate(tokens: list[str]) -> None:
    from .models import PushDevice

    if tokens:
        from django.utils import timezone

        PushDevice.objects.filter(token__in=tokens).update(is_active=False, updated_at=timezone.now())
