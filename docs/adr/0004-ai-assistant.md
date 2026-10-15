# ADR-0004: AI assistant grounded in permission-checked tools, with confirmations

**Status:** proposed · **Date:** 2026-10-15

**Decision:**
* **Engine:** Claude via the official `anthropic` Python SDK, using the Messages API with
  client-side tools in our own loop. Server-side refusal fallback is enabled. The model comes
  from env and defaults to `claude-opus-5-5`; per-route effort is set explicitly.
* **Grounding:**
  * Facts come only from tools that call the same permission-checked services as the REST API
    (scoped to the requesting user), and from a curated knowledge base searched with Postgres
    full-text search.
  * The system prompt forbids figures that don't come from tool results.
* **Actions:**
  * Tools that change state return a *proposal*. Execution needs an explicit user confirmation
    (a button in the app or web, or "YES" on WhatsApp).
  * Money actions additionally need the transaction PIN, or a gateway payment link on WhatsApp.
* **Safety:**
  * Tool results and user text are treated as untrusted (injection defence).
  * Per-user and per-org rate limits and monthly cost caps.
  * Escalation to a human for disputes, payment issues, emergencies and low confidence.
  * The emergency script points to the police and 112, and offers the panic alert.
* **Observability:** every turn is logged (tokens, cost, latency, tools, flags), with redaction
  and deletion on request.
* **Quality gate:** an evaluation set of at least 100 questions per role (seven roles) and a
  scoring script; results are reported before each release.

**Open:** a cheaper model for high-volume WhatsApp routes is your decision after we measure
quality and cost on the evaluation set.
