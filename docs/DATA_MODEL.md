# Homesika: Data model (Phase 0 draft)

> Conventions:
> * **Keys and timestamps:** every table has a UUID primary key plus `created_at` and
>   `updated_at`.
> * **Money:** `*_amount` columns are `BIGINT` minor units (kobo), always paired with a
>   `currency` column, either on the row or inherited from the organization.
> * **Sensitive data:** 🔒 marks columns encrypted at rest (AES-256-GCM).
> * **Delivery:** the phase in which each table is built is shown in brackets.
> * **Integrity:** constraints (unique, check, foreign keys) are enforced in the database, not
>   only in Python.

## 1. Identity, organizations, compliance [Phase 1]

```mermaid
erDiagram
  USER ||--o{ MEMBERSHIP : has
  ORGANIZATION ||--o{ MEMBERSHIP : has
  USER ||--o{ DEVICE : trusts
  USER ||--o{ CONSENT : gives
  USER ||--o{ DATA_REQUEST : files
  ORGANIZATION ||--o{ SETTLEMENT_ACCOUNT : "paid into"
  ORGANIZATION ||--o{ AUDIT_LOG : scopes
  USER ||--o{ AUDIT_LOG : acts

  USER { uuid id; string phone_e164 UK; string email; string first_name; string last_name; string language; string country; string login_pin_hash; string txn_pin_hash; bool phone_verified; bool email_verified; bool is_staff }
  ORGANIZATION { uuid id; string name; string kind "landlord|agency|estate|platform"; string country; string currency; string timezone; string plan; bool is_active }
  MEMBERSHIP { uuid id; uuid user_id FK; uuid organization_id FK; string role "owner|manager|agent|accountant|estate_admin|security|viewer"; string status; uuid invited_by }
  DEVICE { uuid id; uuid user_id FK; string device_id; string secret_hash; string push_token; string platform; datetime revoked_at }
  CONSENT { uuid id; uuid user_id FK; string purpose "terms|privacy|marketing|location|whatsapp"; string version; datetime granted_at; datetime withdrawn_at }
  DATA_REQUEST { uuid id; uuid user_id FK; string kind "export|delete"; string status; datetime completed_at }
  SETTLEMENT_ACCOUNT { uuid id; uuid organization_id FK; string gateway; string subaccount_code; string bank_code; string account_number_last4; string account_number "🔒"; string account_name; string status }
  AUDIT_LOG { uuid id; uuid actor_id; uuid organization_id; string action; string object_type; uuid object_id; json changes; string ip; datetime at }
```

* `OTP_CHALLENGE` (sign-up, new device, PIN reset) and the login-PIN lockout counters on `USER`
  are reused from Goldia.
* An `AUDIT_LOG` row is append-only and written by services for every sensitive action: money,
  roles, data exports, panic alerts and admin actions.

## 2. Properties, leasing, payments: Module A [Phase 1]

```mermaid
erDiagram
  ORGANIZATION ||--o{ PROPERTY : owns
  ESTATE |o--o{ PROPERTY : "may contain"
  PROPERTY ||--o{ UNIT : has
  ORGANIZATION ||--o{ TENANT_PROFILE : keeps
  USER |o--o{ TENANT_PROFILE : "linked when tenant joins app"
  UNIT ||--o{ LEASE : "let via"
  TENANT_PROFILE ||--o{ LEASE : signs
  LEASE ||--o{ CHARGE : generates
  CHARGE ||--o{ ALLOCATION : "settled by"
  PAYMENT ||--o{ ALLOCATION : covers
  PAYMENT_LINK ||--o{ PAYMENT : "paid via"
  PAYMENT ||--o| RECEIPT : issues
  ORGANIZATION ||--o{ EXPENSE : logs
  ORGANIZATION ||--o{ STATEMENT : receives
  GATEWAY_EVENT }o--o| PAYMENT : confirms

  PROPERTY { uuid id; uuid organization_id FK; uuid estate_id FK; string name; string address; string city; string state; string country; string kind }
  UNIT { uuid id; uuid property_id FK; string label; int bedrooms; string kind; bigint default_rent_amount; string status "vacant|occupied|unavailable"; string meter_number; string disco }
  TENANT_PROFILE { uuid id; uuid organization_id FK; uuid user_id FK; string full_name; string phone_e164; string email; string next_of_kin "🔒"; string id_document "🔒"; string notes }
  LEASE { uuid id; uuid unit_id FK; uuid tenant_profile_id FK; date start_date; date end_date; bigint rent_amount; string rent_frequency "monthly|quarterly|biannual|annual"; bigint service_charge_amount; bigint deposit_amount; string status "draft|active|ended|terminated"; string document_file }
  CHARGE { uuid id; uuid organization_id FK; uuid lease_id FK; uuid dues_plan_id FK; uuid unit_id FK; string kind "rent|service_charge|deposit|dues|other"; date period_start; date period_end; date due_date; bigint amount; bigint amount_paid; string status "open|part_paid|paid|waived|void"; string currency }
  PAYMENT_LINK { uuid id; uuid organization_id FK; uuid payer_user_id; string reference UK; bigint amount; bigint fee_amount; string currency; string gateway; string url; string status; datetime expires_at }
  PAYMENT { uuid id; uuid organization_id FK; uuid payment_link_id FK; string gateway; string gateway_reference UK; string channel; bigint amount; bigint gateway_fee_amount; bigint platform_fee_amount; string status "pending|succeeded|failed|reversed|refunded"; datetime paid_at; json verified_payload }
  ALLOCATION { uuid id; uuid payment_id FK; uuid charge_id FK; bigint amount }
  RECEIPT { uuid id; uuid payment_id FK; string number "per-org sequence"; string pdf_file; datetime sent_at; string sent_via }
  EXPENSE { uuid id; uuid organization_id FK; uuid property_id FK; uuid unit_id FK; string category; bigint amount; date spent_on; string vendor; string receipt_file }
  STATEMENT { uuid id; uuid organization_id FK; date period_start; date period_end; json totals; string pdf_file; text ai_summary }
  GATEWAY_EVENT { uuid id; string gateway; string event_id UK; string event_type; bool signature_valid; json payload; string status; int attempts; datetime processed_at }
```

* **Arrears** are derived, not stored: open or part-paid charges whose `due_date` has passed.
  An index on `(organization_id, status, due_date)` keeps that query fast.
* **One `CHARGE` table** serves both rent (`lease_id`) and estate dues (`dues_plan_id`), so
  payments, receipts, reminders and arrears logic are written once.
* **Allocation** lets one payment cover several charges (part-payments and arrears first), with
  a check that the allocated total is no more than the payment.
* **No balance columns for users.** Money we never hold is never represented as a balance.

## 3. WhatsApp, listings, AI assistant: Module B [Phase 2]

```mermaid
erDiagram
  CONTACT |o--o| USER : "may be"
  CONTACT ||--o{ CONVERSATION : in
  USER |o--o{ CONVERSATION : in
  CONVERSATION ||--o{ MESSAGE : contains
  MESSAGE_TEMPLATE ||--o{ MESSAGE : renders
  ORGANIZATION ||--o{ LISTING : publishes
  UNIT |o--o{ LISTING : advertises
  LISTING ||--o{ LEAD : attracts
  CONTACT ||--o{ LEAD : is
  LEAD ||--o{ VIEWING : books
  CONVERSATION ||--o{ ASSISTANT_TURN : has
  ASSISTANT_TURN ||--o{ TOOL_ACTION : proposes
  CONVERSATION ||--o{ ESCALATION : raises
  KB_ARTICLE ||--o{ KB_CHUNK : "split into"

  CONTACT { uuid id; string wa_id UK; string phone_e164; string name; uuid user_id FK; string opt_in_status; datetime opted_in_at }
  CONVERSATION { uuid id; string channel "app|web|whatsapp"; uuid user_id; uuid contact_id; uuid organization_id; string language "en|pcm|fr"; string status; datetime last_inbound_at }
  MESSAGE { uuid id; uuid conversation_id FK; string direction; string kind; text body; string media_file; string provider_message_id UK; string status "queued|sent|delivered|read|failed"; uuid template_id }
  MESSAGE_TEMPLATE { uuid id; string name; string language; string category; string provider_status; json components }
  LISTING { uuid id; uuid organization_id FK; uuid unit_id FK; string title; text description; bigint price_amount; string price_period; json photos; string status; bool ai_generated }
  LEAD { uuid id; uuid organization_id FK; uuid listing_id FK; uuid contact_id FK; string source; string stage; uuid assigned_to }
  VIEWING { uuid id; uuid lead_id FK; uuid listing_id FK; datetime slot_start; string status; uuid agent_id }
  ASSISTANT_TURN { uuid id; uuid conversation_id FK; string model; int input_tokens; int output_tokens; int cache_read_tokens; bigint cost_microusd; int latency_ms; json guardrail_flags; float confidence }
  TOOL_ACTION { uuid id; uuid turn_id FK; string tool; json arguments; bool needs_confirmation; datetime confirmed_at; string status "proposed|confirmed|executed|rejected|failed"; json result }
  ESCALATION { uuid id; uuid conversation_id FK; string reason "dispute|payment|emergency|low_confidence|user_request"; uuid assigned_to; string status }
  KB_ARTICLE { uuid id; uuid organization_id "null = platform-wide"; string title; text body; string language; string status; string audience_roles }
  KB_CHUNK { uuid id; uuid article_id FK; text content; tsvector search_vector }
```

Per-user and per-org usage (tokens, cost, requests) is aggregated per day in `ASSISTANT_USAGE`,
which is what enforces the cost caps.

## 4. Bills: Module C [Phase 3]

```mermaid
erDiagram
  USER ||--o{ BILL_TARGET : saves
  UNIT |o--o{ BILL_TARGET : "meter per unit"
  BILLER ||--o{ BILL_PRODUCT : offers
  USER ||--o{ BILL_PURCHASE : makes
  BILL_PURCHASE ||--o{ PROVIDER_ATTEMPT : "tried with"
  BILL_PURCHASE ||--o| PAYMENT : "paid by"
  BILL_PURCHASE ||--o| REFUND : "refunded by"

  BILL_TARGET { uuid id; uuid user_id FK; uuid unit_id FK; string service "airtime|data|cable_tv|electricity"; string number; string label; string disco }
  BILLER { uuid id; string service; string name; string slug; bool is_active }
  BILL_PRODUCT { uuid id; uuid biller_id FK; string name; bigint amount; bigint cost_amount; json provider_codes }
  BILL_PURCHASE { uuid id; uuid user_id FK; uuid unit_id FK; uuid biller_id FK; uuid product_id FK; string customer_number; bigint amount; bigint fee_amount; string status "awaiting_payment|paid|processing|delivered|refunding|refunded|failed"; string token "🔒"; string idempotency_key UK }
  PROVIDER_ATTEMPT { uuid id; uuid purchase_id FK; string provider; string request_id UK; string status; bigint cost_amount; json response; int latency_ms }
  REFUND { uuid id; uuid payment_id FK; bigint amount; string gateway_reference; string status }
```

* **Order of operations:** pay through the gateway first, then buy. Each failed provider attempt
  moves on to the next provider (failover). After the final failure, the payment is refunded to
  source.
* Homesika's VTU float (prepaid with each provider) is tracked in the internal ledger and is
  **not** customer money.

## 5. Maintenance and artisans: Module D [Phase 4]

```mermaid
erDiagram
  UNIT ||--o{ TICKET : has
  USER ||--o{ TICKET : raises
  TICKET ||--o{ TICKET_EVENT : logs
  TICKET ||--o{ TICKET_PHOTO : has
  TICKET ||--o{ JOB : "assigned as"
  ARTISAN_PROFILE ||--o{ JOB : takes
  JOB ||--o| RATING : "rated by"
  USER ||--o| ARTISAN_PROFILE : is
  ARTISAN_PROFILE ||--o{ VERIFICATION_CHECK : passes
  ARTISAN_PROFILE ||--o{ VOUCHER : "vouched by (guarantor or reference)"

  TICKET { uuid id; string reference "R + 8 hex"; uuid organization_id FK; uuid unit_id FK; uuid lease_id FK; uuid tenant_id FK; uuid raised_by FK "null on WhatsApp without an account"; string category "= artisan trade"; string priority "low|normal|urgent|emergency"; text description; string status "awaiting_approval|approved|assigned|in_progress|done|confirmed|rejected|cancelled" }
  TICKET_EVENT { uuid id; uuid ticket_id FK; uuid actor_id; string kind; text note; datetime at }
  TICKET_PHOTO { uuid id; uuid ticket_id FK; string image "private storage, EXIF removed"; string stage "report|completion" }
  ARTISAN_PROFILE { uuid id; uuid user_id FK; json trades; json service_areas; string verification_status "pending|verified|suspended|removed"; datetime verified_at; float rating_avg; int jobs_completed }
  VERIFICATION_CHECK { uuid id; uuid artisan_id FK; string kind "id|phone|address"; string status "not_started|processing|pending|passed|failed"; string provider "NIN provider|ai|nin+ai|manual|otp"; string id_number "🔒"; string date_of_birth "🔒"; string document "private, deleted 90 days after passing"; json evidence "🔒 match results only, no NIN record"; datetime review_requested_at; datetime checked_at; uuid checked_by }
  VOUCHER { uuid id; uuid artisan_id FK; string kind "guarantor|reference"; string full_name; string phone_e164; string relationship; string address "🔒"; string status "pending|confirmed|declined|expired"; string token_hash "SMS link"; datetime responded_at }
  JOB { uuid id; uuid ticket_id FK; uuid artisan_id FK; string status "offered|accepted|declined|on_site|completed|confirmed|cancelled"; datetime offer_expires_at; datetime scheduled_for; datetime completed_at }
  RATING { uuid id; uuid job_id FK; uuid rater_id; int score; text comment }
```

* The **Verified badge** is shown only when all of these pass: the ID check, phone and address,
  two confirmed guarantors and one reference. It's given and taken away automatically as checks
  change; staff can suspend an artisan, which removes it.
* One active job per ticket (database constraint). Ratings are 1–5 and one per job.
* **Payments for jobs are out of scope** until gateway and legal confirmation.

## 6. Estates, dues and security: Module E [Phase 5, built]

```mermaid
erDiagram
  ORGANIZATION ||--o{ ESTATE : manages
  PROPERTY ||--|| ESTATE : "houses are its units"
  ESTATE ||--o{ ESTATE_MEMBER : has
  USER |o--o{ ESTATE_MEMBER : is
  UNIT |o--o{ ESTATE_MEMBER : "lives in"
  TENANT_PROFILE |o--o{ ESTATE_MEMBER : "pays dues as"
  ESTATE ||--o{ DUES_PLAN : defines
  DUES_PLAN ||--o{ DUES_CHARGE : "one per member and period"
  DUES_CHARGE ||--|| CHARGE : is
  ESTATE ||--o{ ANNOUNCEMENT : posts
  ESTATE ||--o{ GATE_PASS : issues
  GATE_PASS ||--o{ GATE_EVENT : logs
  ESTATE ||--o{ PANIC_ALERT : receives
  PANIC_ALERT ||--o{ ALERT_DELIVERY : "fanned out as"
  PANIC_ALERT ||--o{ INCIDENT_NOTE : logs
  USER ||--o{ PUSH_DEVICE : has

  ESTATE { uuid id; uuid organization_id FK; uuid property_id FK; string name; string join_code UK; bool panic_enabled; bool alert_residents; string gate_instructions }
  ESTATE_MEMBER { uuid id; uuid estate_id FK; uuid user_id FK "null until they sign up"; string phone_number; uuid unit_id FK; string house_label; string role "resident|exco"; string status "pending|approved|suspended|removed"; uuid payer_id FK }
  DUES_PLAN { uuid id; uuid estate_id FK; string name; bigint amount "kobo"; string frequency; date start_date; bool is_active }
  DUES_CHARGE { bigint id; uuid plan_id FK; uuid member_id FK; uuid charge_id FK; date period_start "unique with plan+member" }
  ANNOUNCEMENT { uuid id; uuid estate_id FK; string title; text body; string audience "all|exco"; bool urgent; int push_sent; int sms_sent }
  GATE_PASS { uuid id; uuid estate_id FK; uuid host_id FK; string visitor_name; string visitor_phone; string kind "visitor|artisan|delivery"; uuid job_id FK; string code "6 digits, unique while active"; datetime valid_from; datetime valid_to; int max_uses; int uses; string status }
  GATE_EVENT { uuid id; uuid gate_pass_id FK; string kind "check_in|check_out|denied"; uuid by FK; string note }
  PANIC_ALERT { uuid id; uuid estate_id FK; uuid raised_by FK "null for a WhatsApp-only resident"; uuid member_id FK; string kind; bool silent; text location "🔒 encrypted, consented only"; string status; string client_id UK; datetime acknowledged_at; datetime responding_at; datetime closed_at; string close_note }
  ALERT_DELIVERY { uuid id; uuid alert_id FK; uuid user_id FK; string phone_number; string audience "staff|resident|raiser"; string channel "push|sms|ws"; string status "queued|sent|delivered|acknowledged|failed"; string push_token; string provider_ref; uuid fallback_for FK; datetime sent_at; datetime delivered_at }
  INCIDENT_NOTE { uuid id; uuid alert_id FK; uuid author_id FK; string kind "note or the status it moved to"; text note }
  PUSH_DEVICE { uuid id; uuid user_id FK; string token UK; string platform; bool is_active }
```

* **Dues are ordinary charges** (`kind=dues`) on the estate's units, charged to a payer record made on
  approval, so they're paid, receipted and reconciled like rent.
* **Staff are organization members** (roles `estate_admin`, `security`, plus owner and manager), not
  estate members.
* **Rate limit:** `PANIC_MAX_PER_HOUR` alerts per person (drills excluded). False alarms are counted
  per raiser over 90 days and shown on the desk.
* **Delivery-time metric:** from the alert's `created_at` to the first `delivered_at` per channel
  (push: Expo receipt; SMS: the SMS provider accepted it; `acknowledged`: the app reported it).

## 7. Platform: notifications and analytics [Phase 1+]

* `NOTIFICATION { id, user_id, channel push|sms|email|whatsapp, template, payload, status,
  provider_ref, sent_at, delivered_at, error }`: one row per message we send, for receipts,
  delivery tracking and cost.
* `ANALYTICS_EVENT { id, name, user_id, organization_id, properties jsonb, occurred_at }`:
  product events. Success metrics are computed from operational tables, not only from events.
