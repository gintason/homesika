"""
LLM behind one interface. ASSISTANT_PROVIDER picks the adapter:

* "anthropic": Claude through the official `anthropic` SDK (model from ANTHROPIC_MODEL, default
  claude-opus-5-5). Server-side refusal fallback is on (`fallbacks: "default"`), and the request
  prefix (tools + system) is prompt-cached.
* "mock": MOCK for development and tests. A tiny rule-based stand-in that exercises the tool loop;
  every reply starts with "MOCK:". It is not an assistant and is never used in production.
"""

import json
import logging
import re
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol

from django.conf import settings

logger = logging.getLogger(__name__)

FALLBACK_BETA = "server-side-fallback-2026-07-01"

# USD per million tokens: input, output, cache read, cache write (5-minute). Override with
# ASSISTANT_PRICES. Used for cost caps and reporting only; the invoice is the source of truth.
DEFAULT_PRICES = {
    "claude-opus-5-5": ("4.00", "20.00", "0.20", "5.00"),
    "claude-sonnet-5-5": ("2.00", "10.00", "0.20", "2.50"),
    "claude-haiku-5-5": ("0.10", "0.50", "0.01", "0.125"),
    "mock": ("0", "0", "0", "0"),
}


class LlmUnavailable(Exception):
    """The model couldn't be reached or rejected the request (rate limit, outage, bad request)."""


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass
class LlmResponse:
    content: list[dict]  # assistant content blocks, ready to append to history unchanged
    stop_reason: str
    model: str
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    latency_ms: int = 0
    refusal_category: str | None = None
    fallback_used: bool = False

    @property
    def cost_usd(self) -> Decimal:
        prices = {**DEFAULT_PRICES, **(getattr(settings, "ASSISTANT_PRICES", None) or {})}
        p_in, p_out, p_read, p_write = (Decimal(x) for x in prices.get(self.model, prices["claude-opus-5-5"]))
        return (
            Decimal(self.input_tokens) * p_in
            + Decimal(self.output_tokens) * p_out
            + Decimal(self.cache_read_tokens) * p_read
            + Decimal(self.cache_write_tokens) * p_write
        ) / Decimal(1_000_000)


class LlmClient(Protocol):
    name: str

    def create(
        self,
        *,
        system: list[dict],
        messages: list[dict],
        tools: list[dict] | None = None,
        effort: str = "medium",
        max_tokens: int = 4096,
        output_schema: dict | None = None,
    ) -> LlmResponse: ...


def echoable(content: list[dict]) -> list[dict]:
    """Content to replay in history. After a mid-output fallback, blocks before the last `fallback`
    marker that the fallback model can't continue from are dropped (thinking, tool_use, unpaired
    server-tool blocks); text blocks and everything after the marker are kept, per the API's rules."""
    idx = max((i for i, b in enumerate(content) if b.get("type") == "fallback"), default=None)
    if idx is None:
        return content
    keep_before = [b for b in content[:idx] if b.get("type") == "text"]
    return [*keep_before, *content[idx:]]


class AnthropicLlm:
    name = "anthropic"

    def __init__(self):
        import anthropic

        self._anthropic = anthropic
        # Credentials come from ANTHROPIC_API_KEY in the environment; never from code or the repo.
        self.client = anthropic.Anthropic(timeout=60.0, max_retries=2)
        self.model = settings.ANTHROPIC_MODEL

    def create(self, *, system, messages, tools=None, effort="medium", max_tokens=4096, output_schema=None):
        a = self._anthropic
        output_config: dict = {"effort": effort}
        if output_schema:
            output_config["format"] = {"type": "json_schema", "schema": output_schema}
        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
            "output_config": output_config,
            "cache_control": {"type": "ephemeral"},  # caches the whole prefix for the next turn
            "betas": [FALLBACK_BETA],
            "fallbacks": "default",
        }
        if tools:
            kwargs["tools"] = tools
        started = time.monotonic()
        try:
            resp = self.client.beta.messages.create(**kwargs)
        except a.RateLimitError as exc:
            raise LlmUnavailable("rate limited") from exc
        except a.BadRequestError as exc:
            logger.error("Claude rejected the request: %s", getattr(exc, "message", exc))
            raise LlmUnavailable("bad request") from exc
        except a.APIStatusError as exc:
            raise LlmUnavailable(f"HTTP {exc.status_code}") from exc
        except a.APIConnectionError as exc:
            raise LlmUnavailable("unreachable") from exc
        latency = int((time.monotonic() - started) * 1000)
        content = resp.to_dict().get("content", [])
        usage = resp.usage
        stop_details = getattr(resp, "stop_details", None)
        iterations = getattr(usage, "iterations", None) or []
        return LlmResponse(
            content=echoable(content),
            stop_reason=resp.stop_reason or "",
            model=resp.model,
            text="".join(b.get("text", "") for b in content if b.get("type") == "text"),
            tool_calls=[
                ToolCall(id=b["id"], name=b["name"], input=b.get("input") or {})
                for b in content
                if b.get("type") == "tool_use"
            ],
            input_tokens=usage.input_tokens or 0,
            output_tokens=usage.output_tokens or 0,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
            latency_ms=latency,
            refusal_category=getattr(stop_details, "category", None)
            if resp.stop_reason == "refusal"
            else None,
            fallback_used=any(getattr(i, "type", "") == "fallback_message" for i in iterations),
        )


# ---- MOCK ---------------------------------------------------------------------------------------------

_RULES = [
    (r"\b(fire|robbery|robber|thief|thieves|attack|kidnap|danger|bleeding|emergency)\b", "__emergency__"),
    (r"\b(human|person|customer care|real agent|talk to someone|somebody)\b", "escalate_to_human"),
    (r"\b(receipt|receipts|payments? history|my payments)\b", "list_my_payments"),
    (r"\b(owe|owing|balance|how much|remain|outstanding)\b", "get_my_rent_summary"),
    (r"\b(arrears|who (?:dey )?owe|debtors)\b", "list_arrears"),
    (r"\b(lease|tenancy|agreement)\b", "get_my_lease"),
    (r"\b(link|pay now|send me link)\b", "create_my_payment_link"),
    (r"\b(summary|portfolio|vacant|occupancy|dashboard)\b", "get_portfolio_summary"),
    (r"\b(lead|leads)\b", "list_leads"),
    (r"\b(viewings?|inspections?)\b", "list_viewings"),
    (r"\b(flat|apartment|house|self-contain|listing|bedroom)\b", "search_listings"),
    (r"\b(how|what|help)\b", "search_help"),
]


def _fill(schema: dict, values: dict) -> dict:
    out = {}
    for name, prop in (schema.get("properties") or {}).items():
        if name in values:
            out[name] = values[name]
            continue
        types = prop.get("type")
        types = types if isinstance(types, list) else [types]
        if "null" in types:
            out[name] = None
        elif "enum" in prop:
            out[name] = prop["enum"][0]
        elif "boolean" in types:
            out[name] = False
        elif "integer" in types:
            out[name] = prop.get("minimum", 1)
        elif "array" in types:
            out[name] = []
        elif "object" in types:
            out[name] = _fill(prop, {})
        else:
            out[name] = "MOCK"
    return out


def _sample(schema: dict) -> object:
    t = schema.get("type")
    if t == "object":
        return {k: _sample(v) for k, v in (schema.get("properties") or {}).items()}
    if t == "array":
        return [_sample(schema.get("items") or {"type": "string"})]
    if t == "integer":
        return 1
    if t == "boolean":
        return False
    return "MOCK " + (schema.get("description") or "text")[:40]


class MockLlm:
    name = "mock"

    def create(self, *, system, messages, tools=None, effort="medium", max_tokens=4096, output_schema=None):
        if output_schema:
            text = json.dumps(_sample(output_schema))
            return LlmResponse(
                content=[{"type": "text", "text": text}], stop_reason="end_turn", model="mock", text=text
            )
        last = messages[-1]
        blocks = (
            last["content"]
            if isinstance(last["content"], list)
            else [{"type": "text", "text": last["content"]}]
        )
        results = [b for b in blocks if b.get("type") == "tool_result"]
        if results:
            joined = " | ".join(str(b.get("content"))[:400] for b in results)
            return self._text(f"MOCK: {joined}")
        text = " ".join(b.get("text", "") for b in blocks if b.get("type") == "text").lower()
        names = {t["name"]: t for t in tools or []}
        org = re.search(r"organization_id=([0-9a-f-]{36})", " ".join(s.get("text", "") for s in system))
        for pattern, tool in _RULES:
            if not re.search(pattern, text):
                continue
            if tool == "__emergency__":
                if "escalate_to_human" in names:
                    return self._tool(
                        names["escalate_to_human"],
                        {"reason": "emergency", "summary": text[:200]},
                        prefix="MOCK: Call 112 now. ",
                    )
                return self._text("MOCK: Call 112 now.")
            if tool == "create_my_payment_link" and tool not in names and "send_payment_link" in names:
                continue
            if tool in names:
                values = {"query": text[:100], "summary": text[:200], "reason": "user_request"}
                if org:
                    values["organization_id"] = org.group(1)
                return self._tool(names[tool], values)
        return self._text("MOCK: I can help with rent, payments, receipts and listings.")

    @staticmethod
    def _text(text: str) -> LlmResponse:
        return LlmResponse(
            content=[{"type": "text", "text": text}], stop_reason="end_turn", model="mock", text=text
        )

    @staticmethod
    def _tool(tool: dict, values: dict, prefix: str = "") -> LlmResponse:
        call = ToolCall(
            id=f"toolu_mock_{tool['name']}", name=tool["name"], input=_fill(tool["input_schema"], values)
        )
        content = ([{"type": "text", "text": prefix}] if prefix else []) + [
            {"type": "tool_use", "id": call.id, "name": call.name, "input": call.input}
        ]
        return LlmResponse(
            content=content, stop_reason="tool_use", model="mock", text=prefix, tool_calls=[call]
        )


_CLIENTS = {"anthropic": AnthropicLlm, "mock": MockLlm}


def client() -> LlmClient:
    return _CLIENTS[settings.ASSISTANT_PROVIDER]()
