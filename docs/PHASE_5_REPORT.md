# Phase 5 report: Estates, gate passes and the panic alert

**Date:** 2026-10-17 · **Status:** awaiting your review ("Continue" starts Phase 6)

## Phase 4 decisions applied
* **NIN provider: Smile ID.** It has an official Python SDK (`smile-id-core`), so the adapter is
  built on Smile ID's own code instead of guesses. It's pan-African and offers biometric checks for
  later.
  * The response field names are still `TODO(verify)`. They get confirmed with
    `python manage.py smileid_check` once you have sandbox keys (steps in `docs/DEPLOY_RENDER.md`,
    Phase 4).
* **Privacy notice** at `/privacy` (and `docs/PRIVACY_NOTICE.md`). It names Anthropic and every
  other processor.
  * Phase 5 adds estate data, push tokens, consent-only alert location and Expo.
  * It is still a **draft for a lawyer's review**.

## Delivered

### Estates (backend `apps/estates`)
* **Setup:** an estate is run by an organization (kind "estate association", or a manager).
  * Its houses are units of one property, so **dues are ordinary charges**. They show in the
    resident's Charges and are paid with the same checkout, with receipts and reconciliation.
* **Residents:**
  * A resident joins in the app with the estate's **join code** and their house.
  * The estate office approves them, which makes them a **verified resident**, or adds them
    directly by phone.
  * Admin-added residents are linked to their account automatically when they sign up.
  * Residents can be suspended or removed.
* **Dues plans:** an amount and frequency, charged to every verified resident from the period they
  joined.
  * Generation is safe to rerun.
  * Reminders go at 3 days before, on the day, and at 7 and 30 days late, by WhatsApp (new optional
    template `dues_reminder`) or SMS, with a pay link when the estate has a payout account.
* **Announcements:**
  * Push to residents with the app, SMS to the rest.
  * "Urgent" also sends SMS to everyone.
  * The executive committee can be addressed on its own.
* **Gate passes:**
  * A resident makes a pass with a 6-digit code, a time window and a number of entries (1 to 50).
  * The visitor gets the code by SMS.
  * Security checks the code, then checks the visitor in or out or turns them away, and the host
    is told on arrival.
  * Artisan passes linked to a repair job show the Verified badge at the gate.
* **Roles:** new capabilities.
  * `estate.view` / `estate.manage`;
  * `security.view` / `security.respond`;
  * `gate.verify`.
  * The **Security desk** role sees alerts and the gate only, not money or residents. The
    **Estate admin** role runs the estate.

### Panic alerts (backend `apps/security`)
* **Raising an alert:**
  * Verified residents and estate staff can raise one.
  * The phone sends its own id, so **a retry on a bad network returns the same alert**. A second
    press within 2 minutes joins the open alert instead of starting another.
  * More than 5 in an hour is refused with "call 112".
* **Silent mode:** only security and managers are told, and **nothing is ever sent back to the
  raiser's phone**.
* **Location:** stored **encrypted, only if the person switched on "Share my location"**.
* **Delivery:** every alert runs on its own Celery queue (`alerts`), with a separate worker.
  * **Security desk screens** update at once over WebSocket.
  * **Security and managers** get a push **and** an SMS at the same time.
  * **Residents** (non-silent, if the estate allows) get a push. People without the app get an SMS.
  * **SMS fallback:** if a push **fails** (or the phone is no longer registered), or **Expo doesn't
    confirm it within 45 seconds**, an SMS goes out. The fallback never sends twice.
* **Delivery tests and timings:** every attempt is a delivery row (who, channel, sent, delivered or
  seen, error, and which push an SMS replaced).
  * Each alert shows the seconds to first delivery per channel, staff reached, and the time until
    security saw it.
  * The estate report shows the median time to first delivery over 30 days.
  * **Test alerts:** "Send a test alert" sends a clearly marked TEST to staff only, so an estate can
    prove delivery works before it's needed.
* **Lifecycle:** Seen → On our way → Resolved or False alarm (a note is required), or the raiser's
  "I'm safe".
  * Every step goes into the incident log, and the raiser is told (unless the alert was silent).
  * False alarms are counted per person over 90 days and shown to security.
* **Push infrastructure:**
  * phones register their Expo push token (`/me/push-devices/`); tokens are removed on sign-out
    and dropped when Expo says the device is gone;
  * the Expo adapter is built on Expo's official server SDK; a labelled mock is used in tests, and
    production refuses it.

### The assistant
* **New tools:**
  * `my_estate` (house, dues owed, news);
  * `create_gate_pass` (after **YES**);
  * `raise_panic_alert` (after **YES**; works on WhatsApp even for a resident with no app account);
  * `list_estate_alerts` (staff).
* **Emergencies:** 112 first, then it offers the alert. The app's hold button stays the fastest way.
* **Help article** "Estates: joining, dues, gate passes and the panic button", in English and
  Pidgin.
* **Evaluation:** a new `resident` scenario (Adaeze Nwankwo, Palm Grove Estate, A1, owes ₦15,000)
  and **114 items** (41% Pidgin). The set is now **718**.

### Web (dashboard)
* **Estates:**
  * a list, and creating an estate with its houses;
  * residents: approve (choosing the house), add, suspend, remove;
  * houses, dues plans (pause or resume), announcements (with how many were reached by app and by
    SMS);
  * settings: panic on/off, alert neighbours, gate instructions; join code and new code.
* **Security desk** (live):
  * open alerts with house, raiser, phone, silent warning, map link and false-alarm count;
  * actions; a sound and a screen-reader announcement for new alerts;
  * a "Live / Reconnecting" badge. It polls every 15 seconds anyway, so a dropped connection never
    hides an alert;
  * history, test alert, and the 30-day report.
* **Alert detail:** delivery timings, a table of every delivery, the incident log and notes.
* **Gate:** check a code, see the host and house (and the Verified artisan), let in, check out or
  turn away; the gate log.
* **Colour:** the desk uses the normal danger colour. **Emergency red stays reserved for the panic
  button.**

### Mobile
* **Estate screen** (from Home):
  * **The panic button** in emergency red. Hold it for 2 seconds; a fill shows progress, letting go
    early cancels, and there's a vibration (none in silent mode).
  * **Screen readers:** double tap, then confirm (holding is hard with TalkBack or VoiceOver).
  * Switches for **Silent** and **Share my location** (asked only when switched on; the choice is
    remembered).
  * **Call 112** is always on screen.
  * A failed send retries with the **same alert id**, then shows "Call 112 now" with Try again.
* **After sending:** the live status ("Security is on the way"), "What's happening?" choices, and
  "I'm safe now".
* **Also on the estate screen:** dues owed with a link to pay, gate passes (create and share the
  code, cancel), estate news, and joining with a code.
* **Push notifications:**
  * the phone registers after sign-in;
  * alerts use a loud Android channel that shows on the lock screen;
  * a tapped alert opens its screen and tells the desk it was received.
  * **Guards** see the alert details with "I've seen it" and "On my way". Neighbours get a safety
    message.
* **New packages** (Expo SDK 57 versions): `expo-notifications`, `expo-location`, `expo-haptics`,
  `expo-device`. Permission texts are in `app.json`.
* **Languages:** English and Pidgin throughout.

## Tested (run here)

| Check | Result |
|---|---|
| Backend lint and format | Clean |
| Backend tests, SQLite **and Postgres 16** | **235 passed** on each (205 at the end of Phase 4) |
| Migrations up to date; OpenAPI schema in sync and valid (0 warnings) | OK |
| `check --deploy --fail-level WARNING` (production settings) | No issues; production refuses the mock push |
| **Delivery tests** (mock push and mock SMS): staff push + SMS, resident push, SMS for residents without the app, a dead token → SMS at once and the token switched off, no receipt yet → wait then SMS, error receipt → failed, never two fallback SMS, SMS marked delivered once sent, "received" from the app | Tested |
| Silent alerts: staff only, nothing to the raiser even after "seen"; test alerts staff only and marked TEST; same alert on retry and on a second press; rate limit says 112; who may raise and see | Tested |
| Live desk WebSocket: token in the first message, wrong role refused, foreign website refused, new alert arrives | Tested (in-memory channel layer) |
| Estates: join, approve, dues per period, reminders at each stage (once), announcements push/SMS split, gate code check-in → host told, expired and cancelled passes, other organizations can't see | Tested |
| Assistant: resident tools, gate pass and WhatsApp panic alert after YES (resident with no app account) | Tested (scripted model) |
| Evaluation runner on the 114 new items, **mock model** | No errors (score not meaningful) |
| Web: TypeScript, ESLint, Vitest, build | Pass (**113 tests**) |
| Mobile: TypeScript, ESLint, Jest; Android export | Pass (**116 tests**); 4.9 MB bundle |

## Not tested

* **Real push delivery.** The EAS project isn't created yet (`extra.eas.projectId` is empty), so the
  app can't get a real Expo token.
  * How fast and how reliably alerts arrive on real phones (Doze, battery savers, Do Not Disturb,
    iOS) is **unknown until we test on devices**. This is the most important open item for this
    phase.
* **Real SMS delivery times** with Termii, including a burst to a whole estate. Today "delivered" for
  SMS means the provider accepted it, not that the phone got it (delivery reports are a
  `TODO(verify)`).
* **On a real phone:** the hold gesture, haptics, location permission and accuracy, the lock-screen
  alert channel, TalkBack and VoiceOver on the panic button, and `tel:112`.
* The WebSocket through Render's proxy, and Redis as the channel layer (tests use the in-memory one).
* The assistant against the live Claude API on the 114 new items.

## Risks and open questions

1. **Panic alerts are safety-critical, and Homesika is not an emergency service.** Every screen and
   message says to call 112.
   * Before any estate relies on it, run **test alerts with real phones** and look at the delivery
     timings.
   * Should the estate's terms say this in writing? (A lawyer question.)
2. **Who should neighbours be?** Today a non-silent alert goes to every verified resident when the
   estate allows it (the default). Large estates may prefer only exco, or only the same street.
   Keep the default, or turn it off by default?
3. **Staff always get SMS as well as push** (`PANIC_SMS_STAFF_ALWAYS=true`). This is safest, but each
   alert costs one SMS per staff member. OK?
4. **SMS fallback time:** 45 seconds without an Expo receipt. Shorter means more SMS cost; longer
   means slower help. OK?
5. **iOS Critical Alerts** (sound through silent mode) need an Apple entitlement. Should we apply?
   Without it, a phone on silent may not ring.
6. **Gate codes are 6 digits**, unique among an estate's active passes, and checks are limited to 60
   a minute per guard. Should we add a QR code later, or is the code enough at your gates?
7. **Stored money:** none. Dues are paid through the same payment links as rent. Nothing is held.

## Next steps that need you

* **Expo:**
  * create the EAS project (`npx eas init` in `mobile/`) and add FCM and APNs credentials;
  * optionally set `EXPO_ACCESS_TOKEN` in Render (never in chat).
* **Render:** sync the blueprint so the new **alerts worker** starts. Without it no alert push or
  SMS goes out.
* Answer the questions above. Then "Continue" for Phase 6.

## Decisions after review

1. Neighbours: keep the default (non-silent alerts go to every verified resident when the estate
   allows it).
2. Staff get SMS as well as push: yes (`PANIC_SMS_STAFF_ALWAYS=true`).
3. SMS fallback after 45 seconds: yes.
4. iOS Critical Alerts: yes, apply to Apple. The app and server are ready for it behind a switch
   (Phase 6: `PUSH_IOS_CRITICAL_ALERTS`, off until Apple grants the entitlement).
5. A 6-digit gate code is enough (no QR code).
