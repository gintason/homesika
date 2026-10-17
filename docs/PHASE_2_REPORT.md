# Phase 2 report: WhatsApp toolkit and the Claude assistant

**Date:** 2026-10-17 · **Status:** awaiting your review ("Continue" starts Phase 3: bills)

## Delivered

### WhatsApp (backend `apps/messaging`)
* **Meta WhatsApp Cloud API adapter,** plus a labelled mock:
  * a signed webhook (signature check and verification handshake);
  * inbound messages stored exactly once;
  * delivery statuses (sent, delivered, read, failed).
* **Opt-in and opt-out:**
  * messaging us opts a person in; STOP opts them out and START opts them back in;
  * an app toggle does the same;
  * opt-in and opt-out are recorded as NDPA consent.
* **The 24-hour rule:** free-form messages only within 24 hours of the person's last message;
  templates outside that window.
* **Reminders, receipts and payment links** go by WhatsApp when the person has opted in **and**
  an approved template exists; otherwise they go by SMS. A failed WhatsApp delivery falls back to
  SMS once. The template texts to submit are in `docs/WHATSAPP_TEMPLATES.md`.
* **Escalations and a staff inbox:**
  * the organization's owners and managers get an SMS alert;
  * staff can take over a conversation (the assistant goes silent), reply, and hand back.

### Listings (backend `apps/listings`)
* **Listings with photos.** Photos are stored in S3-compatible storage (Cloudflare R2 or S3), or
  on local disk in development.
* **Public search and listing pages.** The exact address is hidden until a viewing is booked.
* **Leads:** enquiries are captured from WhatsApp, the app and the web, with one lead per
  person per listing. The team gets an SMS on each new enquiry.
* **Viewings:** slots with capacity, bookings that can't double-book a slot, and confirmations.
  Unpublish, archive and mark-as-let actions are included.
* **AI listing writer:**
  * takes the facts and up to 4 photos and returns a title, description, WhatsApp caption,
    features and suggested replies;
  * uses structured outputs and is told never to invent anything;
  * its output is always a draft that the agent edits.

### The assistant (backend `apps/assistant`, spec in `docs/ASSISTANT.md`)
* **One service for WhatsApp, the app chat and the web chat.**
* **Model:** Claude through the official `anthropic` SDK (1.15.0).
  * Model `claude-opus-5-5`, set by `ANTHROPIC_MODEL`, at explicit `medium` effort.
  * Server-side refusal fallback is on (`fallbacks: "default"`).
  * The request prefix is prompt-cached.
  * Tools use strict JSON schemas.
* **Role-aware:** tenant, landlord, staff (manager, agent, accountant, viewer, each with its own
  capabilities) or prospect.
  * The person is identified by our code (login or WhatsApp number), never by the model.
  * There are 18 tools in all, and each checks permissions the same way the REST API does.
* **Grounded:** facts come only from tool results and the knowledge base. The knowledge base has
  12 topics in English and Pidgin, organizations can add their own articles, and it is searched
  with Postgres full-text search.
* **Confirmations:**
  * payment links and viewing bookings are only *proposed*;
  * **our code**, not the model, carries them out after a "YES" or a tap on Confirm;
  * proposals expire after 15 minutes, and anything other than a yes cancels them.
* **Escalation** for disputes, payment problems, complaints, requests for a person, low
  confidence, emergencies, refusals and spending limits. Emergencies tell the person to call
  **112** first.
* **Guardrails enforced in code:**
  * a 2,000-character message limit;
  * 20 messages per 10 minutes per sender;
  * daily and monthly spending caps per user, organization and platform;
  * an output filter that removes phone numbers, emails and account numbers that aren't the
    person's own;
  * prompt-injection rules;
  * silence while a person has taken over.
* **Logging:** every model call records tokens, estimated cost, latency, tools and flags (no
  message text). History is append-only per session and replayed unchanged.
* **Evaluation:**
  * **544 questions** across four roles (tenant 183, landlord 120, staff 123, prospect 118), about
    40% in Pidgin;
  * the scenarios are built exactly as in the spec, on a frozen date;
  * a deterministic scorer runs with `python manage.py assistant_eval`.

### Web
* **Listings:**
  * listing management with photos;
  * the AI writer, with "Use this" buttons that fill the form;
  * viewing slots.
* **Leads and viewings:** the leads pipeline and the viewings list.
* **WhatsApp inbox:** take over, reply (respecting the 24-hour rule) and hand back.
* **Public pages:** a lightweight public listing page and search.
* **Help articles** for the assistant, managed per organization.
* **"Ask Homesika" panel** with confirmation cards.

### Mobile (tenant app)
* **Help tab:**
  * assistant chat in English and Pidgin, with confirmation cards and the "a person will reply"
    banner;
  * retry without duplicate messages;
  * pay links that open checkout;
  * the 112 note.
* **Profile:** WhatsApp on/off.
* **Find a place:** search, listing detail, viewing booking and enquiries.

## Tested (run here)

| Check | Result |
|---|---|
| Backend lint and format | Clean |
| Backend tests, SQLite **and Postgres 16** | **131 passed** on each (82 at the end of Phase 1) |
| Migrations up to date; OpenAPI schema in sync and valid | OK |
| `check --deploy --fail-level WARNING` (production settings) | No issues |
| Production refuses the mock assistant, mock WhatsApp and mock gateway | Confirmed |
| Scenario data matches the spec (₦440,000, ₦665,000, receipts, slots…) | Pinned by tests |
| Evaluation runner, all 544 items, **mock model** | Runs end to end with no errors (score not meaningful, see below) |
| The exact Claude request (model, fallbacks, betas, caching, effort, strict tools) | Unit-tested with a fake SDK client |
| Web: TypeScript, ESLint, Vitest, build | Pass (**81 tests**; public pages 2.7 kB gzip, staff chunk 39 kB gzip) |
| Mobile: TypeScript, ESLint, Jest; Android export | Pass (**60 tests**); 4.7 MB Hermes bundle |
| Design tokens | In sync, 18 contrast tests pass |

## Not tested

* **The real assistant's quality.** Nothing has called Claude yet, because there's no API key
  here and the evaluation costs money.
  * The only scored run used the **mock** model: 226/544 (41.5%). This only proves the plumbing
    works.
  * **The real pass rate is the release gate, and it is still unknown.**
  * Run it once you add the key (steps in `docs/DEPLOY_RENDER.md`):
    `python manage.py assistant_eval --limit 20 --yes`, then the full set. Expect roughly 1–3
    model calls per item; the command prints the estimated cost.
* **WhatsApp against Meta.** Meta's docs couldn't be reached from my build environment, so the
  send payloads, webhook format, signature header, Graph API version and template rules are
  written from memory and marked `TODO(verify)`. They are tested only against the mock.
* **Photo storage on R2 or S3.** Only local disk was used.
* **The web app in a browser, and the mobile app on a phone:**
  * chat keyboard behaviour on Android;
  * long-chat scrolling on low-end phones;
  * photo loading from a CDN;
  * screen readers on the new screens;
  * layout at 200% font size.
* **Docker, Render and GitHub Actions** (unchanged from Phase 1).

## Risks

1. **The evaluation score is unknown,** and the scorer is strict on structure but blind to tone.
   It checks tools, amounts, confirmations, escalations, 112 and leaks, and the language with a
   heuristic. Read a sample of real transcripts by hand before letting real tenants use it.
2. **Cost:**
   * Opus-class pricing on a high-volume WhatsApp line can add up;
   * the caps are defaults (US$0.50 per user per day, US$30 per organization per month, US$25 per
     day for the platform), so set them to your budget;
   * moving the WhatsApp FAQ route to a cheaper model is your decision, after comparing evaluation
     scores.
3. **WhatsApp policy:** treating "messaging us first" as opt-in, template categories and pricing
   changes all need checking against Meta's current rules.
4. **A WhatsApp number counts as identity.** A number a landlord added as a tenant can see that
   tenant's rent on WhatsApp without an app account. WhatsApp verifies phone ownership, but SIM
   swaps are a known risk in Nigeria. Mitigation: money actions only create payment links, and
   nothing the assistant does moves money.
5. **Public enquiry and booking forms send SMS** to numbers people type in. They are
   rate-limited per IP; add a CAPTCHA if abuse appears.
6. **The Pidgin needs review.** The help articles, app strings, canned replies and evaluation
   items all need a native speaker to read them.

## Small gaps noted (proposed for later)

* **Inbox:** no unread tracking (the badge counts open escalations), and no paging beyond 200
  messages.
* **Leads and viewings:** no rules on which lead or viewing stage can follow which, and no manual
  "add lead" form in the web app (the endpoint exists).
* **Search:** bedrooms must match exactly (no "4+").
* **Bookings:** a signed-in tenant's booking isn't tied to their account.

## Open questions for you

1. **Anthropic API key:** create one with a monthly limit, then put it in Render (never in chat).
   Should I run the full evaluation on staging, and what budget is OK for it?
2. **WhatsApp:** is the Meta Business account and number ready? Who should receive escalations
   that belong to no organization (`SUPPORT_PHONE`)?
3. **Photo storage:** Cloudflare R2 (recommended: cheap, no egress fees) or AWS S3?
4. **Spending caps:** what daily and monthly limits do you want?
5. **Support hours:** are "Monday to Saturday, 8am to 6pm" right?
6. **Pidgin:** can a native speaker review the Pidgin text before pilots?
7. **Still open from Phase 1:**
   * Paystack's written confirmation on split settlement;
   * the launch city;
   * the platform fee.
