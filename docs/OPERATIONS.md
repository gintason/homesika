# Operations runbook

For whoever runs Homesika day to day. Each section says what to watch, and what to do when something
goes wrong.

## Backups and restore
* **Database:** Render Postgres takes daily backups (point-in-time recovery on paid plans;
  `TODO(verify)` your plan's retention).
  * **Restore drill, every quarter:** restore the latest backup into a new database, point a staging
    API at it, and check that you can sign in and see one landlord's charges.
  * Write down how long it took.
* **Files:** listing photos and the private bucket (repair photos, ID documents) live in S3/R2. Turn on
  versioning on the private bucket, so a deleted file can be recovered for 30 days.
* **Encryption keys** (`FIELD_ENCRYPTION_KEYS`): keep a copy in a password manager that two people can
  open. **Without the key, encrypted columns can't be read**, even from a backup.

## Rotating secrets
* **Encryption key:** put the new key **first** in `FIELD_ENCRYPTION_KEYS` and keep the old one after
  it (comma-separated). New writes use the new key, and old rows still decrypt. Remove the old key only
  after re-saving the old rows (ask for a re-encrypt command when needed).
* **API keys** (Paystack, Flutterwave, VTU.ng, Reloadly, Smile ID, Anthropic, Termii, Meta, Expo):
  change them in Render's Environment, then redeploy. Never paste a key in chat or put it in
  `.env.example`.

## What the system checks for you
* `check --deploy` (in CI and on every deploy) refuses mock providers in production. It also checks
  for:
  * a missing or invalid encryption key (homesika.E002);
  * an empty CORS list (homesika.W003);
  * a missing private bucket (homesika.W001).
* **Daily retention job** (`core-retention`, 03:17 Lagos time) deletes or erases:
  * messages older than 180 days;
  * alert locations 90 days after the alert closes;
  * visitors' phone numbers 90 days after their gate pass ends;
  * switched-off push devices.
* Sentry gets errors with no personal data (`send_default_pii=False`).

## When something goes wrong
* **Panic alerts not reaching phones:**
  1. Is the **alerts worker** running? (Render → `homesika-staging-alerts`.)
  2. Open the alert in the Security desk. The delivery table shows push sent/delivered/failed and SMS
     for every person.
  3. All pushes "failed": check `EXPO_ACCESS_TOKEN` and the Expo status page. SMS is the fallback, so
     check the Termii balance too.
  4. Run **Send a test alert** after any fix.
* **"VTU.ng float is empty" or "Reloadly balance is empty"** in the logs (critical): fund the account.
  Until then, orders fail over to the next provider or are refunded automatically.
* **Payment gateway down:** links fail over from Paystack to Flutterwave automatically. Watch for
  payments in **needs review** (amount or currency mismatch) in the admin.
* **Bills stuck in "processing" or "needs review":** the reconciliation job re-checks every 5 minutes.
  Anything still in review after an hour needs a person: check the provider's dashboard by the order's
  `request_id`, then mark it delivered or refund it.
* **A Smile ID / AI check is stuck:** it goes to a person after 6 hours, under Artisans → Verification
  checks.

## Numbers to look at weekly
* **Dashboard → Analytics** (each organization): collection rate, paid on time, arrears.
* **Homesika's own numbers:** `GET /api/v1/platform/metrics/` (staff accounts only), or
  `python manage.py platform_metrics`. They cover:
  * active users;
  * rent and dues paid online;
  * platform fees;
  * bills delivered and their fees;
  * referrals and free fees used.
