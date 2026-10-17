# Phase 4 report: Maintenance tickets and artisans

**Date:** 2026-10-17 · **Status:** awaiting your review ("Continue" starts Phase 5: estate dues, gate
passes and the panic alert)

## Delivered

### Repair tickets (backend `apps/maintenance`)
* **Reporting:**
  * A tenant reports a repair for a home they rent now, from the app or on WhatsApp through the
    assistant.
  * WhatsApp works even without an app account, when the landlord added them by phone.
  * Each report has a category, a priority (low, normal, urgent or emergency), a description,
    access notes and up to 6 photos.
  * A double tap or a retry on a weak network returns the same request instead of creating a
    second one.
* **Landlord decision:** owners and managers approve or reject (a reason is required). Agents can
  manage repairs but can't approve them.
  * Staff can also log a repair themselves. It's approved at once.
  * Staff can mark a repair as fixed without an artisan ("fixed another way"), and the tenant still
    confirms.
* **Assigning an artisan:** only a **Verified, available** artisan can be assigned. The picker
  filters by trade and area, and puts artisans the landlord has used before first.
  * The artisan has 24 hours to accept. If they decline or don't answer, the ticket goes back to the
    landlord to choose someone else.
  * Assigning someone else cancels the open offer, and the first artisan is told.
* **Doing the job:** the artisan accepts (with a visit time, or "I'll call to agree a time"),
  arrives, and finishes with a note and photos.
  * **Before accepting** they see only the area and the problem. The address and the tenant's first
    name and phone appear **only after they accept**.
* **Tenant confirms, then rates:** the tenant confirms the fix or says "not fixed". "Not fixed" goes
  back to the same artisan.
  * If the tenant doesn't answer, they get one reminder after 2 days, and the repair is confirmed
    automatically after 7 days.
  * Ratings are 1–5 stars, once per job, and feed the artisan's average and job count.
* **Status updates:** the tenant, artisan and staff get WhatsApp or SMS messages at each step.
  * New templates: `ticket_update` and `job_offer` (in `docs/WHATSAPP_TEMPLATES.md`).
  * Urgent reports are flagged in the staff alert. Emergencies remind the person to call **112**.
* **Timeline and comments:** every step is logged. Staff can add **internal** notes that the
  tenant and artisan never see. Each ticket tells the app what the viewer can do next.
* **Background job:** `maintenance-housekeeping` runs every 30 minutes. It expires unanswered
  offers, sends the confirmation reminder, and confirms old repairs automatically.
* **Payments:** none. Quotes and job payments stay out of scope until gateway and legal
  confirmation. The apps say so.

### Artisan onboarding and the Verified badge (backend `apps/artisans`)
* **Sign-up:** a business name, trades, the areas they work in, and their address (encrypted, never
  shown to landlords or tenants). **Consent to the checks is required and recorded** (NDPA).
* **Checks behind the badge:**
  * **ID:** the artisan uploads a photo of the ID, and Homesika staff review it in the admin. This
    `manual` mode is the default and is safe in production. A labelled `mock` exists for
    development, and production refuses it. **No ID-provider API is built**, because none has been
    chosen; it's marked `TODO(verify)`.
  * **Phone:** passed automatically, because sign-up already confirms it by OTP.
  * **Address:** staff confirm it in the admin. Changing the address means it has to be confirmed
    again.
  * **Two guarantors and one reference:** each gets an **SMS link** (`/v/<token>`) to a small public
    page where they confirm or say no.
    * Links expire after 14 days, can be resent up to 3 times (10 minutes apart), and only a hash of
      each link is stored.
    * The page shows only the artisan's business name and trades.
* **The badge itself:** it's given automatically once every check passes, and removed if one stops
  passing. Staff can suspend an artisan, which also removes it, or reinstate them.

### Private photos (all of Phase 4)
* **Photos are re-encoded on upload**, which **drops EXIF data, including the GPS location** most
  phones add. A test proves a photo carrying GPS is stored without it.
* **Size:** photos are shrunk to 2048 px. The app shrinks them to 1600 px before upload, for weak
  networks.
* **Separate storage:** repair photos and ID documents are kept in private storage. They're served
  only through **15-minute signed links** that the API hands out after its own permission check; on
  S3 or R2 these are presigned URLs.
* **Deploy check:** it warns if `S3_PRIVATE_BUCKET` (a bucket with no public access) isn't set.

### The assistant
* **New tools:**
  * `report_repair`: an action, so the request is created only after **YES**;
  * `my_repairs`: status, artisan, Verified badge and visit time;
  * `list_repairs`: for staff.
* **Prompt rules:** for danger, tell the person to get safe and call 112 first. Approving and
  assigning are done in the dashboard. No invented prices or dates.
* **Help articles:** two new ones (Reporting a repair; What "Verified artisan" means), in English
  and Pidgin.
* **Evaluation:** **34 new items**, so the set is now **604** (tenant 223, landlord 127, staff 127,
  prospect 127). The scenario data has Chidi's tap (assigned to Kunle Plumbing Works, visiting
  Friday 2pm) and Grace's light (waiting for approval).

### Web (dashboard)
* **Repairs:**
  * a list with status filters, priority badges, tenant and artisan;
  * a detail page with photos, the timeline (internal notes marked), the artisan card, approve,
    reject, assign (artisan picker), fixed another way, cancel, confirm (only when there's no
    tenant in the app), comments and photos;
  * "Log a repair".
* **Public guarantor and reference page** (`/v/<token>`): a 1 kB chunk, plain language, with a
  privacy note.
* **Permissions test:** it now **reads the backend's permission matrix directly**, so the web
  copy can't drift from it.

### Mobile (tenant and artisan)
* **Tenants:**
  * a **Repairs** card on Home;
  * the list, and a report form with camera or gallery photos (shrunk on the phone), the 112
    warning and a **Call 112** button for emergencies;
  * the detail screen with the Verified artisan, visit time and a call button (once they've
    accepted);
  * actions: confirm or "not fixed", star rating, cancel, messages and photos.
* **Artisans** (Profile → Work as an artisan):
  * sign-up with consent;
  * the checklist, an ID check with a photo, and guarantors and references (resend or remove);
  * a "Taking new jobs" switch;
  * jobs: accept with a visit time, decline, arrive, finish with a note and photo, and messages.
* **Languages:** English and Pidgin throughout.
* **New packages:** `expo-image-picker` and `expo-image-manipulator`, at the versions Expo pins for
  SDK 57. They're set up in `app.json` with camera and photo permission prompts.

## Phase 3 decisions applied
* NGN 100 fee on electricity and cable TV by default, and none on airtime or data. The app shows it
  before payment.
* **No daily limit** (`BILLS_DAILY_LIMIT` defaults to 0).
* `expo-clipboard` for copying tokens.
* Your VTU.ng agreement is noted in the Phase 3 report. The VTU.ng wallet isn't funded yet, so
  keep the bills mock on staging.

## Tested (run here)

| Check | Result |
|---|---|
| Backend lint and format | Clean |
| Backend tests, SQLite **and Postgres 16** | **184 passed** on each (155 at the end of Phase 3) |
| Migrations up to date; OpenAPI schema in sync and valid (0 warnings) | OK |
| `check --deploy --fail-level WARNING` (production settings) | No issues; the private-bucket warning appears when only `S3_BUCKET` is set |
| Production refuses the mock ID check | Confirmed |
| The full repair flow (report → approve → assign → accept → arrive → finish → confirm → rate), decline, offer expiry, reassign, reopen, reminder and auto-confirm, staff-created repairs, internal notes, permissions per role, the artisan seeing no address before accepting | Tested |
| Verification: consent, encrypted address, manual and mock ID checks, guarantor links (confirm, decline, expiry, resend limits, no private data on the page), badge given and taken away, suspension, the directory | Tested |
| Photos: EXIF/GPS removed, non-images refused, at most 6, signed links (work, tampered → 404, expired → 404) | Tested |
| Assistant: a WhatsApp report without an app account after YES; tool permissions; scenario data | Tested (mock model) |
| Evaluation runner on the 34 new items, **mock model** | No errors. The **full 604-item mock run** also finished with no errors (score not meaningful) |
| Web: TypeScript, ESLint, Vitest, build | Pass (**101 tests**; the guarantor page is a 0.95 kB gzip chunk) |
| Mobile: TypeScript, ESLint, Jest; Android export | Pass (**99 tests**); 4.9 MB bundle |

## Not tested

* **On a real phone:**
  * the camera and gallery, and the permission prompts;
  * photo shrinking (only mocked under Jest);
  * calling from the app (`tel:` links);
  * photo uploads on a slow network.
* **Real storage:** private files on S3 or R2, including the presigned links. Only local disk was
  used.
* **Real messages:** SMS and WhatsApp to tenants, artisans and guarantors (mock SMS only). The
  WhatsApp templates aren't approved yet, so these messages go by SMS for now.
* **The real assistant** on repair conversations: there's still no API key.
* **Any ID-provider API.** None was built (see Risks).
* **On real hardware and infrastructure:** the web pages in a browser, and Docker, Render and CI.

## Risks

1. **ID checks are manual.** Staff must look at each ID photo. That's fine for a pilot, but it
   doesn't scale and can't check the NIN against NIMC. Choose a provider (Prembly, Dojah, Smile ID,
   QoreID…) and sign a data-processing agreement first. I'll add the adapter once you share their
   documentation.
2. **Guarantor quality:** an artisan can name friends who'll click yes. The link proves the phone
   number answered, nothing more. Consider a short call to one guarantor before the badge, or
   accept the risk for the pilot.
3. **Sensitive data:** ID photos, ID numbers (encrypted), addresses (encrypted) and guarantor
   details are kept. Set up the private bucket before real artisans sign up. Decide how long to keep
   ID photos after a check passes (the proposed default is to delete them 90 days after it passes;
   this isn't built yet).
4. **Auto-confirm after 7 days** could mark something "fixed" that isn't. The tenant gets a
   reminder at day 2 first. Change `MAINTENANCE_AUTO_CONFIRM_DAYS` if you prefer.
5. **Safety:** the artisan gets the tenant's phone and address after accepting. Only Verified
   artisans can be assigned, every step is on the ticket's timeline, and landlord decisions go to
   the audit log. Estate gate passes in Phase 5
   will add a check at the gate.
6. **The Pidgin needs review,** including the new repair and artisan text.

## Small gaps (proposed for later)
* Landlords can't invite their own trusted artisan from the dashboard yet. The artisan signs up in
  the app instead.
* No push notifications yet (Phase 5 sets up push); updates go by SMS and WhatsApp.
* Server messages are English only.
* The artisan directory filters in Python. That's fine for hundreds of artisans; it needs an
  index for thousands.
* No "ticket per month" analytics yet (Phase 6).
* ID photos aren't deleted automatically after the check (see risk 3).

## Open questions for you

1. **ID provider:** which one, and is there a contract or data-processing agreement? Until then,
   checks are manual.
2. **Who reviews artisans?** Which Homesika staff account(s) will approve IDs and addresses in the
   admin, and how fast? (Artisans are told they'll get an SMS.)
3. **Guarantors:** is an SMS link enough, or should Homesika also phone one guarantor before the
   badge?
4. **ID photo retention:** OK to delete ID photos 90 days after the check passes, keeping only the
   type, the last 4 digits and the result?
5. **Auto-confirm:** are 7 days and a reminder at day 2 right?
6. **Private bucket:** please create one (with no public access) alongside the photo bucket when
   you set up storage. R2 or S3 is still open from Phase 2.
7. **Still open:**
   * from Phase 3: funding the VTU.ng wallet;
   * earlier: Paystack's split confirmation, the launch city, the platform fee, the Anthropic key
     and evaluation budget, and WhatsApp Business readiness.

## Decisions after review (applied)

1. **ID check = NIN verification, automated.** The artisan enters their NIN and date of birth and
   adds a photo of their NIN slip or card.
   * The NIN is looked up through a licensed provider (`NIN_PROVIDER`).
   * Claude reads the photo with structured output: document type, name, NIN, date of birth and signs
     of alteration.
   * **Fixed rules in code decide:**
     * NIN not found → fail;
     * name doesn't match the record (order, middle names and small spelling differences allowed)
       → fail;
     * date of birth differs → fail;
     * the number on the photo differs → fail;
     * the photo can't be read → fail (try again);
     * looks altered, name or date on the photo disagrees, or the model isn't sure → **a person
       reviews**;
     * otherwise → pass.
   * The model never decides, and **there's no face comparison**.
   * **Still needed: the NIN provider.** Their docs couldn't be reached from the build environment,
     so only a labelled mock exists and production refuses it (`TODO(verify)`). Choose a provider
     and I'll add the adapter.
2. **Address check, automated.** It passes when the NIN record's address is the same place as the
   one the artisan gave (judged by AI). Otherwise the artisan uploads a bill, bank statement or
   tenancy paper from the last 3 months, and Claude reads it.
   * Wrong address, an old document or no document → fail.
   * A different name on the bill (common with landlords' or relatives' bills), an unsure match or a
     possibly altered document → a person reviews.
3. **Human review on request (NDPA).** After any automatic failure the artisan can tap "Ask a person
   to review". The check then appears in the admin queue with what the automatic check found.
4. **Guarantors:** the SMS link is enough (no change).
5. **ID and address photos are deleted 90 days after the check passes.** The type, the last 4
   digits and the result are kept. This runs hourly.
6. **Auto-confirm:** 7 days with a reminder at day 2 (no change).
7. **Private bucket:** to be created together later.
8. **Consent:** the sign-up consent now names the NIN lookup and the AI reading, and the right to a
   person's review. Anthropic should be listed as a processor of artisan documents in the privacy
   notice.

**Tested:**
* Backend: **202 passed** on SQLite and Postgres. Every rule above is tested with a scripted model.
  Also tested: provider and model outages (the check stays "processing" and is retried), the
  90-day deletion, and the production guard.
* Mobile: **103 tests** pass.

**Not tested:** a real NIN lookup (no provider yet), and Claude reading real NIN slips and bills (no
API key here). Before going live, try a handful of real (consenting) documents on staging.
