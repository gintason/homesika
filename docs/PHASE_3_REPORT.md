# Phase 3 report: Bills (airtime, data, cable TV, electricity)

**Date:** 2026-10-17 · **Status:** awaiting your review ("Continue" starts Phase 4: maintenance and artisans)

## Delivered

### Backend (`apps/bills`)
* **Catalogue:**
  * **Coverage:** MTN, Airtel, Glo and 9mobile airtime and data; DStv, GOtv, StarTimes and
    Showmax; the 12 DisCos, prepaid and postpaid.
  * **Plans and markup:** data and TV plans are synced from VTU.ng (`sync_bills_catalogue`), with
    an optional markup percentage.
  * **Sample plans:** `sync_bills_catalogue --sample` loads sample plans for local testing. They
    are clearly named "(sample)".
* **Pay per transaction, with no stored balance or wallet.**
  * Each order gets its own Paystack or Flutterwave checkout, paid into Homesika's own account. No
    landlord split applies.
  * An order is sent to the VTU provider **only after the gateway confirms the exact amount**. A
    wrong amount goes to review instead.
  * Unpaid orders expire after 60 minutes.
* **Meter and card checks:**
  * meter, smartcard and IUC numbers are checked with the provider before payment, and the
    customer name is shown;
  * the check is repeated on the server when the order is created.
  * A tenant's **meter number and DisCo are saved on the unit** and prefilled.
* **Delivery, failover and refunds:**
  * **Provider order:** providers are tried in the order set in `BILLS_PROVIDERS`. VTU.ng is
    ported from Goldia; the Flutterwave Bills adapter is marked `TODO(verify)`.
  * **Failed or rejected:** the order is sent to the next provider. When none is left, the money
    is **refunded automatically** through the gateway's refund API.
  * **Processing or unknown:** the same provider is re-checked and the order is **never re-sent
    or refunded**. That rule is what prevents paying twice for one top-up. After 12 checks (about 40
    minutes) the order goes to admin review.
  * **Background checks:** a reconciliation job runs every 5 minutes. It re-checks stuck orders,
    retries refunds and expires unpaid orders.
  * **Webhook:** the VTU.ng webhook is signed (HMAC-SHA256) and processed exactly once.
* **Receipts and history:** receipt numbers run BIL-000001, BIL-000002 and so on, with a PDF
  receipt.
  * The electricity token is stored encrypted, and shown only to the buyer once the order is
    delivered.
  * A public status page shows no token.
  * SMS or WhatsApp messages go out for the token, for delivery and for refunds.
* **Limits:**
  * a daily spending limit per user (default ₦200,000);
  * a per-category fee (default ₦0), shown in the catalogue and on every order;
  * 30 requests per minute.
* **Admin:** re-check, refund and clear-review actions, plus every provider attempt kept on the
  order.
* **Production guard:** production refuses the mock bills provider.

### The assistant (WhatsApp, app and web chat)
* **New tools:** `list_bill_options`, `check_meter_or_card`, `buy_bill` and `my_bill_orders`. For
  example, "buy ₦5,000 light for my meter" or "abeg send 1GB MTN to 0803…".
* **`buy_bill` only proposes.** Our code creates the order and the payment link after the person
  replies **YES**. It never spends money by itself.
* **Evaluation:** 26 new items, so the set is now **570**. The scenario data has a meter, a DisCo
  and a delivered token.

### Mobile (tenant app)
* **Bills screen:** airtime, data, TV and electricity, with these steps:
  1. the meter is prefilled from the unit;
  2. the meter or card is checked and the customer name shown;
  3. the person reviews the order;
  4. checkout;
  5. a live status screen with a copyable token and the receipt.
* **Fees:** if a fee applies, the app shows amount + fee = total and asks again before checkout.
* **History:** a list of past bill orders.
* **Languages:** English and Pidgin.

### Web
* **Payment return page:** `/bills/:reference/done` shows the status and the token after
  checkout. It is used by WhatsApp and web payment links.

## Tested (run here)

| Check | Result |
|---|---|
| Backend lint and format | Clean |
| Backend tests, SQLite **and Postgres 16** | **155 passed** on each (131 at the end of Phase 2) |
| Migrations up to date; OpenAPI schema in sync and valid | OK |
| `check --deploy --fail-level WARNING` (production settings, `BILLS_PROVIDERS=vtung,flutterwave`) | No issues |
| Bills flows, with the mock provider and gateway | Tested: happy path, wrong amount, expiry, failover, refund, "unknown" not refunded, stuck order to review, refund retry, daily limit, unit ownership, privacy, webhook duplicates and signature |
| VTU.ng adapter request and response handling | Tested against recorded responses (`responses`), not the live API |
| Evaluation runner, all 570 items, **mock model** | Runs end to end with no errors (score not meaningful) |
| Web: TypeScript, ESLint, Vitest, build | Pass (**91 tests**) |
| Mobile: TypeScript, ESLint, Jest; Android export | Pass (**80 tests**); 4.8 MB bundle |

## Not tested

* **Nothing has been bought for real.** No VTU.ng or Flutterwave Bills call has been made, and no
  real refund.
  * Every flow above ran against the labelled **mock** provider and gateway.
  * Test with small amounts on staging first. The steps are in `docs/DEPLOY_RENDER.md`.
* **Live provider details are unconfirmed:**
  * the VTU.ng webhook field names and the exact Flutterwave Bills endpoints and biller codes are
    marked `TODO(verify)`;
  * the Paystack and Flutterwave **refund** endpoints are also `TODO(verify)`.
* **The real assistant on bill requests** (no API key yet, as in Phase 2).
* **On real hardware and infrastructure:** the app on a phone, the web page in a browser, and
  Docker, Render and CI.

## Risks

1. **Licensing.** Reselling airtime, data and electricity may need a licence or a written
   agreement with the VTU provider. Taking the payment into Homesika's account and then buying
   the service is a "merchant" model. Confirm with your lawyer and VTU.ng that this is allowed,
   and that it is not treated as holding customer funds.
2. **Refunds depend on unverified APIs.** If a refund call fails, the order stays
   "refund pending" and is retried every 5 minutes, and admins can see it. Check those orders
   daily until refunds are proven live.
3. **VTU.ng float.** VTU.ng is pre-funded. If the balance runs out, orders fail over to
   Flutterwave or are refunded. Either way the customer is never charged without delivery, but
   too many refunds would look bad. Set a low-balance alert with VTU.ng.
4. **Stuck orders.** If a provider's "processing" state never resolves, the order goes to review
   after about 40 minutes (12 checks, spaced further apart each time). Someone must look at that admin list.
5. **Gateway fees.** Paystack and Flutterwave fees on small top-ups (₦100–₦500) can be more than
   the VTU margin. Use the per-category fee and minimum amounts to cover this.

## Small gaps (proposed for later)

* **Server-side wording:** error messages and SMS from the server are in English only; the app's
  own text is English and Pidgin.
* **Flutterwave biller codes** must be entered in the admin per biller before Flutterwave
  failover works for that biller.
* **Copy button:** the mobile copy button uses React Native's older Clipboard API.
  `expo-clipboard` is the supported replacement (a one-line change, plus the new package).
* **No "buy again"** on past orders.

## Open questions for you

1. **Licence:** do you have a written agreement or licence status for VTU resale? (See risk 1.)
2. **Fees:** should there be a Homesika fee per category, and how much (e.g. ₦100 on
   electricity)? It is currently ₦0 everywhere.
3. **Daily limit:** is ₦200,000 per user per day right?
4. **VTU.ng:** is the merchant account funded, and are the keys ready? Put them in
   `backend/.env` locally and in Render, never in chat.
5. **expo-clipboard:** OK to add it?
6. **Still open from earlier phases:**
   * Paystack's confirmation on split settlement;
   * the launch city;
   * the platform fee;
   * the Anthropic key and evaluation budget;
   * WhatsApp Business readiness.
