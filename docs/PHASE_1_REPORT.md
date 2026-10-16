# Phase 1 report: rent and landlord MVP

**Date:** 2026-10-16 · **Status:** awaiting your review ("Continue" starts Phase 2)

## Delivered

### Backend (Django API)
* **Accounts:** phone-first sign-up with an SMS OTP, a 6-digit login PIN, trusted devices
  (a new device needs PIN + OTP) and forgot-PIN. Sign-up records consent to terms and privacy,
  and users can request data export or deletion (NDPA).
* **Organizations and roles:** landlord, agency and estate accounts. Roles are owner, manager,
  agent, accountant, estate admin, security and viewer, checked on every request. Staff are
  invited by phone. An audit log records sensitive actions.
* **Rent core:** properties and units; tenants, with next of kin and ID encrypted at rest;
  leases (draft → active → ended or terminated) that generate rent, service-charge and deposit
  charges, with a short final period pro-rated; waivers; arrears; a dashboard.
* **Payments:**
  * **Settlement:** the landlord's own bank account is registered as a gateway subaccount, so
    money settles to the landlord and Homesika holds nothing (ADR-0002).
  * **Paying:** payment links by SMS; checkout tries Paystack then Flutterwave; every payment is
    re-verified with the gateway and recorded exactly once.
  * **Allocation:** oldest charges are paid first, and overpayments are flagged for review.
  * **Receipts:** numbered per organization (`RCT-000001`) as PDFs. Tenant and landlord both get
    an SMS, and the link works without a login.
  * **Recording:** manual cash or transfer payments.
  * **Webhooks and reconciliation:** webhooks are signature-checked, stored once and processed in
    the background. A check every 15 minutes and a daily reconciliation catch missed payments.
* **Rent reminders:** SMS 7 days and 1 day before, on the due day, and 3, 7, 14 and 30 days late.
  Each stage is sent once, and landlords can turn reminders off.
* **Expenses and monthly statements:** billed, collected, spent and net per property, with a CSV
  download.
* **API safety:** `Idempotency-Key` on requests that move money. `docs/openapi.yaml` is the
  contract, and CI fails if it drifts from the code.

### Web (React): landlord and agent dashboard
* **Component library:** built from the design tokens.
* **Sign-in:** sign up and sign in with OTP + PIN, and an organization switcher.
* **Rent screens:** dashboard, properties and units, tenants, leases, charges, arrears.
* **Money screens:** payments (with receipt download), payment links, manual payments, monthly
  statement.
* **Settings:** payout bank account, team, reminder setting, expenses.
* **Public pages** opened from SMS links (about 100 kB gzipped): pay, payment status, receipt,
  and a **clearly labelled test checkout** for the mock gateway.

### Mobile (Expo): tenant app
* **Sign-in:** phone OTP + PIN, app lock with optional fingerprint or face, ported from Goldia and
  adapted.
* **Rent:** my rent (total owed, overdue, next due), charges by landlord, pay through the gateway
  checkout with status polling, payments, receipts (download and share).
* **Language:** English and **Nigerian Pidgin**. The Pidgin is marked for review by a native
  speaker.

### Deployment
* `render.yaml` (Render Blueprint) and `docs/DEPLOY_RENDER.md`.
* Staging starts with the **mock** gateway and mock SMS, so nothing real is charged or sent.

## Tested (run here)

| Check | Result |
|---|---|
| Backend lint + format (ruff) | Clean |
| Backend tests, SQLite **and Postgres 16** | **82 passed** on each |
| Migrations up to date | OK |
| `check --deploy --fail-level WARNING` (production settings) | No issues |
| Production refuses the mock gateway | Confirmed |
| OpenAPI schema generates and matches the committed file | OK |
| Web: TypeScript, ESLint, Vitest, production build | Pass (**54 tests**; build 114 kB + 313 kB JS, 30 + 100 kB gzip) |
| Mobile: TypeScript, ESLint, Jest | Pass (**44 tests**) |
| Mobile: Expo bundle for Android (and iOS, by the mobile build) | Builds (4.6 MB Hermes bundle) |
| Design tokens in sync; 18 contrast tests | Pass |

The backend tests cover:
* **Pay flow:** link, checkout failover, mock payment, idempotent confirmation, partial payments
  and overpayments.
* **Records:** receipts (PDF), manual payments.
* **Webhooks and reconciliation:** bad signatures rejected, webhooks stored once, missed webhooks
  recovered, daily reversal check.
* **Reminders, expenses and statements.**
* **Access control:** cross-organization access (404), role limits (403), Idempotency-Key replays.
* **Gateway adapters:** request building and response parsing, against mocked HTTP.

## Not tested

* **Real Paystack, Flutterwave and Termii.** Only the mock gateway and mock SMS were exercised.
  The adapters were tested against **mocked** responses. Field names I couldn't check against
  live docs are marked `TODO(verify)` in `apps/payments/gateways/*.py` and
  `apps/notifications/sms.py`. The main ones are the **subaccount and split fields**, Termii's
  `channel` and response fields, and the placeholder email for tenants without one.
* **Docker image, `docker compose up`, and a real Render deploy.** There's no Docker daemon here,
  and render.com isn't reachable from my build environment.
* **GitHub Actions on GitHub itself.** It runs when you push.
* **The app in a real browser or phone.** All UI tests use mocked network calls in a simulated
  DOM or React Native test renderer. Not checked: real checkout redirects, receipt
  download/share on a phone, fingerprint/face unlock, SMS code autofill, large-font layouts,
  speed on a cheap Android phone.
* **Load and concurrency.** Locking is in place (charges are row-locked in a fixed order), but it
  was not stress-tested.

## Risks

1. **Split settlement is still unconfirmed.** This is the most important open item. Before live
   keys, get Paystack's written confirmation that subaccount settlement goes **directly** to the
   landlord's bank and counts as no stored value. Do the same for Flutterwave.
2. **Web sign-in keeps the refresh token in localStorage.** If a cross-site-scripting bug ever got
   in, a session could be stolen. Mitigations planned before production: a strict
   Content-Security-Policy on the static site, then moving to httpOnly cookies.
3. **Public pay and receipt links are bearer links.** They use long random references, and anyone
   with the link sees the landlord's name, the amount and the tenant's first name (the receipt
   shows the tenant's full name). That's normal for payment links; links expire after 72 hours.
4. **Idempotency results live in Redis (24 hours).** Losing Redis loses that protection, but not
   the payment rules: payments stay unique per gateway reference.
5. **SMS costs and delivery.** Reminders and receipts are SMS-only for now. WhatsApp arrives in
   Phase 2. The Termii sender ID must be approved.

## Gaps found while building (small; proposed for early Phase 2)

* **No bank list endpoint.** The payout form asks for the bank code by hand. The fix is to proxy
  the gateway's bank list and resolve the account name before saving.
* **After a failed real payment, the public link still reads "pending".** The page can't tell
  "failed" apart from "still processing" except with the mock gateway.
* **The team list doesn't return user ids.** The web app recognises the current user by phone
  number instead.
* **The transaction PIN isn't used anywhere yet.** It will protect bill payments in Phase 3.
* **No server-side translations yet.** The mobile app shows its own English or Pidgin text for
  known error codes.

## Open questions for you

1. **Paystack and Flutterwave:** have you opened the business accounts? When you have **test**
   keys, put them in Render's dashboard (never in chat or GitHub) and I'll test the real flow.
2. **Termii:** has the sender ID "Homesika" been applied for?
3. **Platform fee:** charge nothing for now (the current setting), or a percentage per payment?
4. **Launch city:** Lagos or Abuja first? (Still open from Phase 0.)
5. **Pidgin:** can a native speaker review `mobile/src/i18n/locales/pcm.json`?
6. **Terms and privacy pages:** where will they be published? The app links to them once
   `EXPO_PUBLIC_TERMS_URL` and `EXPO_PUBLIC_PRIVACY_URL` are set.
