# Third-party integrations: verification register

Rule: no endpoint, field or signature scheme is used in real code until it is checked against
the provider's **official** documentation (or a sandbox call). Anything unchecked is marked
`TODO(verify)` in code and listed here. Each integration has a labelled **mock adapter** for
tests and local development.

**Note on this build environment:** the cloud workspace I build in cannot reach most provider
documentation sites. Verification therefore happens in one of two ways:
1. you paste the relevant doc pages, as you did for VTU.ng; or
2. we run the sandbox check scripts on your machine.

| Integration | Purpose | Phase | Status | What must be verified |
|---|---|---|---|---|
| Paystack | Rent, dues and bill payments; split settlement to landlords | 1 | Partly known (Goldia used initialize, verify and webhooks) | **Subaccounts and split** (field names, who bears fees, settlement timing); webhook signature header; refunds API; transfer recipients are *not* needed (no payouts). Also get **written confirmation** that the split setup isn't stored value. |
| Flutterwave | Failover gateway | 1 | Partly known (Goldia) | Subaccounts/split equivalents; webhook hash; refunds; v3 vs v4 API |
| WhatsApp Cloud API (Meta) | Reminders, receipts, inquiries, buy commands | 2 | **Built (Phase 2), `TODO(verify)`**: adapter in `apps/messaging/whatsapp.py` written from memory, Meta's docs unreachable from the build environment; tested only against the mock | Graph API version, send-message payloads, template categories and pricing (blueprint notes per-message pricing changes from 1 Oct 2026), webhook verification and signature, 24-hour session rules, media download |
| Claude API (Anthropic) | AI assistant, listing generator, summaries | 2 | **Built (Phase 2)**: official `anthropic` SDK 1.15.0, `claude-opus-5-5`, server-side refusal fallback, prompt caching, strict tools; request shape unit-tested, **not yet run against the live API** | Model and effort choice per route and the cost model, measured on the evaluation set |
| SMS provider (Termii proposed) | OTP and panic fallback | 1/5 | Partly known (Goldia send) | DND route and sender-ID approval timelines, delivery reports, throughput for alert bursts |
| Push (Expo push vs direct FCM/APNs) | Alerts, reminders | 1/5 | Decision pending | High-priority delivery on Android Doze and iOS critical alerts entitlement (needs Apple approval); delivery receipts |
| VTU provider(s) | Airtime, data, cable TV, electricity | 3 | VTU.ng known (your pasted docs, Goldia) | **Licence status** of each provider, a second provider for failover, refund/requery behaviour |
| ID verification (Prembly / Dojah / Smile ID / QoreID / other) | Artisan NIN check | 4 | Not chosen | Your choice, pricing, NDPA processing terms, response fields |
| Object storage (S3-compatible) | Photos, documents, PDFs | 1 | Standard | Provider choice (AWS S3, Cloudflare R2, DigitalOcean Spaces) |
| Sentry | Error tracking | 0/1 | Standard SDK | DSN per environment |
