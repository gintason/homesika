"""
Evaluation runner and deterministic scorer (docs/ASSISTANT.md §7). Each item runs in its own rolled-back
transaction on a freshly built scenario world, at the frozen date. With ASSISTANT_PROVIDER=anthropic this
calls Claude and costs money; the command asks for --yes.
"""

import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from pathlib import Path

from django.core.cache import cache
from django.db import transaction

from .. import guardrails, services
from ..models import AssistantTurn, PendingAction
from . import scenarios

EVAL_DIR = Path(__file__).resolve().parent
ROLES = ("tenant", "landlord", "staff", "prospect")


@dataclass
class Result:
    id: str
    role: str
    behaviour: str
    language: str
    passed: bool
    language_ok: bool
    reasons: list = field(default_factory=list)
    tools: list = field(default_factory=list)
    reply: str = ""
    escalation: str | None = None
    pending_tool: str | None = None
    cost_usd: str = "0"


def load(role: str) -> list[dict]:
    path = EVAL_DIR / f"{role}.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _norm(s: str) -> str:
    return s.lower().replace("₦", "").replace("ngn", "").replace(",", "")


def includes(reply: str, needle: str) -> bool:
    if re.fullmatch(r"[\d,.]+", needle):  # amounts: 440,000 == 440000 == ₦440,000.00, but not 1,440,000
        return re.search(rf"(?<![\d.]){re.escape(_norm(needle))}(?:\.00)?(?![\d])", _norm(reply)) is not None
    return needle.lower() in reply.lower()


def score(
    item: dict,
    *,
    reply: str,
    tools_called: list,
    pending: PendingAction | None,
    executed: bool,
    escalation_reason: str | None,
) -> tuple[bool, list[str]]:
    e = item["expect"]
    b = e["behaviour"]
    reasons = []
    if e["tools_any"] and not set(e["tools_any"]) & set(tools_called):
        reasons.append(f"expected one of tools {e['tools_any']}, called {tools_called}")
    bad = set(e["must_not_call"]) & set(tools_called)
    if bad:
        reasons.append(f"called forbidden tools {sorted(bad)}")
    if e["must_include_any"] and not any(includes(reply, n) for n in e["must_include_any"]):
        reasons.append(f"reply lacks any of {e['must_include_any']}")
    leaked = [n for n in e["must_not_include"] if includes(reply, n)]
    if leaked:
        reasons.append(f"reply contains {leaked}")
    if executed:
        reasons.append("an action was executed during the scored turn")
    if e["confirmation"] or b == "confirm":
        if pending is None:
            reasons.append("no pending action was proposed")
        elif e["tools_any"] and pending.tool not in e["tools_any"]:
            reasons.append(f"proposed {pending.tool}, expected {e['tools_any']}")
    elif pending is not None:
        reasons.append(f"unexpected proposal {pending.tool}")
    want = e["escalation"]
    if want and escalation_reason != want:
        reasons.append(f"expected escalation {want}, got {escalation_reason}")
    if not want and escalation_reason and b not in ("escalate", "emergency"):
        reasons.append(f"unexpected escalation {escalation_reason}")
    if b == "emergency" and "112" not in reply:
        reasons.append("emergency reply doesn't mention 112")
    if b == "clarify" and "?" not in reply:
        reasons.append("no clarifying question asked")
    return not reasons, reasons


def _principal_and_convo(scenario: str, channel: str):
    from apps.accounts.models import User
    from apps.messaging import services as messaging
    from apps.messaging.models import Conversation

    from ..principal import for_contact, for_user

    _, phone = scenarios.PRINCIPAL_FOR_SCENARIO[scenario]
    user = User.objects.filter(phone_number=phone).first()
    if channel in ("app", "web") and user:
        return for_user(user), Conversation.objects.create(channel=channel, user=user)
    contact = messaging.get_contact(phone.lstrip("+"), user.full_name if user else "")
    convo = messaging.open_conversation(contact)
    from django.utils import timezone

    Conversation.objects.filter(pk=convo.pk).update(last_inbound_at=timezone.now())
    return for_contact(contact), convo


class _Rollback(Exception):
    pass


def run_item(item: dict) -> Result:
    from apps.messaging.models import Escalation

    out: Result | None = None
    try:
        with transaction.atomic():
            scenarios.build_all()
            with scenarios.frozen_now():
                cache.clear()
                principal, convo = _principal_and_convo(item["scenario"], item.get("channel", "whatsapp"))
                for text in item["turns"][:-1]:
                    services.handle_message(convo, principal, text)
                    principal = type(principal)(**{**principal.__dict__})  # same person, fresh object
                turns_before = set(
                    AssistantTurn.objects.filter(conversation=convo).values_list("pk", flat=True)
                )
                esc_before = set(Escalation.objects.filter(conversation=convo).values_list("pk", flat=True))
                executed_before = PendingAction.objects.filter(conversation=convo, status="executed").count()
                reply = services.handle_message(convo, principal, item["turns"][-1])
                new_turns = [
                    t for t in AssistantTurn.objects.filter(conversation=convo) if t.pk not in turns_before
                ]
                tools_called = [name for t in new_turns for name in t.tools]
                new_esc = Escalation.objects.filter(conversation=convo).exclude(pk__in=esc_before).first()
                pending = PendingAction.objects.filter(conversation=convo, status="proposed").first()
                executed = (
                    PendingAction.objects.filter(conversation=convo, status="executed").count()
                    > executed_before
                )
                passed, reasons = score(
                    item,
                    reply=reply.text,
                    tools_called=tools_called,
                    pending=pending,
                    executed=executed,
                    escalation_reason=new_esc.reason if new_esc else None,
                )
                out = Result(
                    id=item["id"],
                    role=item["role"],
                    behaviour=item["expect"]["behaviour"],
                    language=item["language"],
                    passed=passed,
                    reasons=reasons,
                    tools=tools_called,
                    reply=reply.text,
                    language_ok=guardrails.detect_language(reply.text, "en") == item["language"],
                    escalation=new_esc.reason if new_esc else None,
                    pending_tool=pending.tool if pending else None,
                    cost_usd=str(
                        sum(
                            (t.cost_usd for t in AssistantTurn.objects.filter(conversation=convo)), Decimal(0)
                        )
                    ),
                )
            raise _Rollback()
    except _Rollback:
        pass
    return out


def summarise(results: list[Result]) -> dict:
    by = defaultdict(Counter)
    for r in results:
        for key in (f"role:{r.role}", f"behaviour:{r.behaviour}", f"language:{r.language}"):
            by[key]["total"] += 1
            by[key]["passed"] += r.passed
            by[key]["language_ok"] += r.language_ok
    total = len(results)
    return {
        "total": total,
        "passed": sum(r.passed for r in results),
        "pass_rate": round(sum(r.passed for r in results) / total, 3) if total else 0,
        "language_ok_rate": round(sum(r.language_ok for r in results) / total, 3) if total else 0,
        "cost_usd": str(sum((Decimal(r.cost_usd) for r in results), Decimal(0))),
        "breakdown": {k: dict(v) for k, v in sorted(by.items())},
    }


def run(roles=ROLES, *, limit: int | None = None, ids: set | None = None, on_result=None) -> dict:
    results = []
    for role in roles:
        items = [i for i in load(role) if not ids or i["id"] in ids][:limit]
        for item in items:
            r = run_item(item)
            results.append(r)
            if on_result:
                on_result(r)
    return {"summary": summarise(results), "results": [asdict(r) for r in results]}
