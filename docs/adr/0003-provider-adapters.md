# ADR-0003: Every third party behind an interface, with labelled mocks and failover

**Status:** proposed · **Date:** 2026-10-15

**Decision:**
* Each integration (payments, WhatsApp, SMS, push, VTU, ID checks, LLM) is a Python protocol
  with real adapters and a **mock adapter in a `*_mock.py` file**, which logs that it is a mock.
* A registry picks adapters from settings, with an ordered failover list where it makes sense
  (payments, VTU, SMS).
* Real adapters ship only after their fields are verified (see `docs/INTEGRATIONS.md`);
  unverified details carry `TODO(verify)`.
* HTTP calls have timeouts. Only idempotent reads are retried automatically. An unknown outcome
  on a money call is re-checked, never assumed to have failed (a lesson from Goldia).

**Consequences:** tests never call real providers; local development works offline; providers
can be swapped without touching business logic.
