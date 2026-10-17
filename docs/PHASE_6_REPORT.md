# Phase 6 report: Scale

**Date:** 2026-10-17 · **Status:** awaiting your review. Phase 6 is the last phase of the blueprint
roadmap.

The blueprint's Phase 6 was: hardening, analytics, a referral program, international top-ups, a second
city, then a second country. You chose bill fee waivers for referrals, Reloadly for top-ups, Abuja as
the second city, and Ghana as the second country, built but switched off.

## Phase 5 decisions applied
* **Neighbours:** non-silent alerts go to every verified resident (the default is kept).
* **Staff:** get SMS as well as push.
* **SMS fallback:** after 45 seconds.
* **Gate code:** 6 digits is enough.
* **iOS Critical Alerts:** ready behind switches, so you can apply to Apple now. The steps are in
  `docs/DEPLOY_RENDER.md` (Phase 6, step 6).

## Delivered

### Hardening
* **Data retention** (NDPA): a daily job deletes or erases:
  * messages after 180 days;
  * alert locations 90 days after the alert closes;
  * visitors' phone numbers 90 days after the pass ends;
  * dead push devices.
  The privacy notice says so.
* **Speed:** three lists ran one database query per row. These were the estates and alerts lists, and
  the organization's charges list (22 queries for 20 charges). All three are fixed, and tests now fail
  if a list's query count grows with its rows. A sweep of every other list found no other case.
* **Deploy safety:** a deploy now **stops** without a valid encryption key, and warns if the web app's
  address (CORS) is missing.
* **Web security headers:**
  * no framing;
  * nosniff;
  * referrer policy;
  * permissions policy (no camera, microphone or location on the web);
  * HSTS.
* **Dependency audit:**
  * **Python:** one advisory, in Twisted's IMAP mail module. Homesika doesn't use that module (Daphne
    uses Twisted only for the web server), and no fixed version exists yet.
  * **Web:** none.
  * **Mobile:** the warnings are in build and test tooling (Expo CLI, Metro, Jest), not the app.
    npm's suggested "fix" is a downgrade to Expo 44, so I didn't apply it.
* **Runbook** (`docs/OPERATIONS.md`):
  * backups and a quarterly restore drill;
  * key rotation;
  * what to do when alerts, bills or payments fail;
  * weekly numbers to look at.

### Analytics
* **Dashboard → Analytics** (owners, managers, accountants, viewers):
  * Month by month (3, 6 or 12 months): **billed vs collected**, **collection rate**, **paid on
    time**, dues collected.
  * Today: occupancy, overdue amount and how many tenants owe, open repairs and the median days to
    fix, leads and viewings, emergency alerts and false alarms.
* **The chart:**
  * Its colours were checked with a palette validator (colour-blind separation and contrast).
  * Bars have keyboard and hover tooltips, and a table shows every number.
  * On phones it scrolls inside its card, so the text stays readable.
* **Homesika's own numbers** (staff accounts only, `/platform/metrics/` or
  `python manage.py platform_metrics`):
  * users and active users;
  * rent and dues paid online;
  * platform fees;
  * bills delivered and their fees;
  * referrals and free fees used.

### Referrals (free bill service fees)
* **How it works:**
  * Everyone has a code (Profile → **Invite friends**: share or copy it).
  * A new person who signs up with it gets their **next 3 electricity or cable TV service fees free**
    (₦100 each).
  * When they make a **first real purchase** (a delivered bill, or rent or dues paid online), the
    inviter also gets 3.
* **Not money:** free fees have no cash value, can't be withdrawn or transferred, and expire after 6
  months.
* **Never lost:** a free fee used on an order that isn't paid, or is refunded, is given back.
* **Abuse limits:**
  * each account needs its own verified phone;
  * you can't use your own code;
  * a code can be added only to a new account (within 14 days, before any purchase);
  * at most 20 rewarded invites a month per person (more are recorded as "capped").
* **Invite links:** `/join?code=…` on the web opens the app with the code filled in, or signs up on the
  web.
* **Checkout:** shows "Free (invite reward)" and pays the lower total. It never pays more than the
  person saw without asking again.

### Airtime abroad (Reloadly)
* **For the person:** Bills → **Airtime abroad**. Choose the country (Ghana, Kenya, South Africa, UK,
  US, Canada and more) and enter the number.
  * **The network is found on the server from the number**, and the naira amount is checked against
    the network's limits.
  * The app shows an **estimate** of what arrives, clearly labelled as one.
* **Same machinery as other bills:** it uses the same pay-first, then deliver pipeline, with failover,
  automatic refunds and receipts.
* **Reloadly adapter:**
  * It's built from **Reloadly's official SDK code**: the URLs, auth, version header, endpoints and
    request body all come from there. Their documentation site couldn't be reached from here.
  * The SDK hides all errors, so we call the HTTP API directly. That way every outcome is handled
    safely: "never created" leads to a refund, "may exist" leads to a requery, and nothing is ever
    bought twice.
* **Without Reloadly keys:** a labelled **SAMPLE** catalogue lets you try it in development.
  Production refuses Reloadly's sandbox.

### Abuja and Ghana
* **One markets table** (`docs/MARKETS.md`).
* **Abuja is on:**
  * the listing form offers the city;
  * its neighbourhoods are suggested (Wuse 2, Maitama, Garki, Gwarinpa…);
  * Abuja electricity (AEDC) was already in the bills catalogue.
* **Ghana is built but switched off:**
  * GHS, +233 numbers read correctly in a Ghana organization, and the Accra time zone;
  * no Ghana organization can be created until `MARKETS_COUNTRIES` includes GH;
  * `docs/MARKETS.md` lists the 8 things to do before switching it on (payments in GHS, a bills
    provider, Ghana Card checks, SMS sender ID, emergency numbers, Ghana's data protection
    registration, legal review, Twi).

### Help and privacy
* **Assistant help articles:** "Invite friends" and "Airtime abroad", in English and Pidgin.
* **Privacy notice:** now covers referral data, Reloadly (the recipient's number abroad) and the
  retention rules. It is still a draft for legal review.

## Tested (run here)

| Check | Result |
|---|---|
| Backend lint and format | Clean |
| Backend tests, SQLite **and Postgres 16** | **270 passed** on each (235 at the end of Phase 5) |
| Migrations up to date; OpenAPI schema in sync and valid (0 warnings) | OK |
| `check --deploy --fail-level WARNING` | No issues with keys and CORS set. The missing-key error and the CORS warning appear without them. Production refuses Reloadly's sandbox |
| Retention job (each rule, and nothing deleted twice) | Tested |
| Query-count tests (estates, residents, alerts, gate, announcements, dues, charges) | Tested. Reverting a fix makes the test fail |
| Analytics against the scenario data (₦665,000 overdue across 3 tenants); paid on time; staff-only platform metrics | Tested |
| Referrals: sign-up with code, free fee applied, referrer rewarded on the first delivered bill and on an online rent payment, given back when unpaid or refunded, own code, second code, old account, monthly cap, redeem later, expiry | Tested |
| Airtime abroad: countries, lookup, delivered order, 6 kinds of bad input, switched off; Reloadly adapter against mocked HTTP (auth body, headers, top-up body, "never created" vs "may exist", requery, token refresh) | Tested |
| Markets: Abuja on, Ghana off then on (currency and time zone), Ghana phone numbers | Tested |
| Web: TypeScript, ESLint, Vitest, build; Analytics rendered and checked on desktop and phone | Pass (**117 tests**) |
| Mobile: TypeScript, ESLint, Jest; Android export | Pass (**123 tests**); 4.9 MB bundle |

## Not tested

* **Reloadly for real:** the sandbox reply fields are `TODO(verify)`. That's the transaction id and
  status on success, the history endpoint used to requery, and which error codes mean "never created".
* **On real phones and the live web:** the referral share sheet, the invite link opening the app
  (`homesika://register?code=…`), and airtime abroad end to end.
* **GHS payments** through Paystack/Flutterwave (Ghana is off).
* **Load testing:** I fixed per-row queries and added tests, but didn't run a load test. That needs
  staging with realistic data.

## Risks and open questions

1. **Reloadly account currency.** The account must be funded in **naira**, so prices are in NGN.
   Can Reloadly fund an NGN account for you, or is it USD only? If it's USD only, we need an exchange
   rate and margin policy before switching it on.
2. **A fee on airtime abroad?** Today there's none (your ₦100 fee is on electricity and cable TV
   only). International top-ups have thin margins, so do you want a fee, or a small percentage?
3. **Referral reward size:** 3 free fees each (₦300 of our fee). Keep it, or change it? The numbers
   are settings.
4. **Ghana:** who will handle the GHS payments confirmation and Ghana's data protection registration?
5. **Apple Critical Alerts:** you said yes. The request needs an Apple developer account in the
   company's name.

## Next steps that need you

* **Render:** sync the blueprint (new settings and web headers).
* **Reloadly:** create the account (in naira if possible), put the sandbox keys in Render (never in
  chat), and buy one sandbox top-up. Then I'll confirm the `TODO(verify)` fields.
* **Apple:** request the Critical Alerts entitlement.
* **Backups:** do the first restore drill (`docs/OPERATIONS.md`).
