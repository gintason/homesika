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
  TICKET ||--o{ ATTACHMENT : has
  TICKET ||--o{ JOB : "assigned as"
  ARTISAN_PROFILE ||--o{ JOB : takes
  JOB ||--o| RATING : "rated by"
  USER ||--o| ARTISAN_PROFILE : is
  ARTISAN_PROFILE ||--o{ VERIFICATION_CHECK : passes
  ARTISAN_PROFILE ||--o{ GUARANTOR : "vouched by"
  ARTISAN_PROFILE ||--o{ REFERENCE : "referenced by"

  TICKET { uuid id; uuid organization_id FK; uuid unit_id FK; uuid raised_by FK; string category; string priority; text description; string status "open|awaiting_approval|approved|assigned|in_progress|done|confirmed|rejected|cancelled" }
  TICKET_EVENT { uuid id; uuid ticket_id FK; uuid actor_id; string kind; text note; datetime at }
  ATTACHMENT { uuid id; string owner_type; uuid owner_id; string file; string mime; int bytes }
  ARTISAN_PROFILE { uuid id; uuid user_id FK; json trades; json service_areas; string verification_status "pending|verified|suspended|removed"; datetime verified_at; float rating_avg; int jobs_completed }
  VERIFICATION_CHECK { uuid id; uuid artisan_id FK; string kind "id|phone|address"; string provider; string result; json evidence "🔒"; datetime checked_at }
  GUARANTOR { uuid id; uuid artisan_id FK; string name; string phone_e164; string relationship; string address "🔒"; datetime confirmed_at }
  REFERENCE { uuid id; uuid artisan_id FK; string kind "landlord|estate"; uuid referee_org_id; string status }
  JOB { uuid id; uuid ticket_id FK; uuid artisan_id FK; string status "offered|accepted|declined|scheduled|on_site|completed|confirmed"; datetime scheduled_for; datetime completed_at }
  RATING { uuid id; uuid job_id FK; uuid rater_id; int score; text comment }
```

* The **Verified badge** is shown only when all of these pass: the ID check, phone and address,
  two confirmed guarantors and one reference.
* **Payments for jobs are out of scope** until gateway and legal confirmation.

## 6. Estates, dues and security: Module E [Phase 5]

```mermaid
erDiagram
  ORGANIZATION ||--o{ ESTATE : manages
  ESTATE ||--o{ ESTATE_MEMBER : has
  USER ||--o{ ESTATE_MEMBER : is
  UNIT |o--o{ ESTATE_MEMBER : "lives in"
  ESTATE ||--o{ DUES_PLAN : defines
  DUES_PLAN ||--o{ CHARGE : generates
  ESTATE ||--o{ ANNOUNCEMENT : posts
  ESTATE ||--o{ GATE_PASS : issues
  ESTATE ||--o{ PANIC_ALERT : receives
  PANIC_ALERT ||--o{ ALERT_DELIVERY : "fanned out as"
  PANIC_ALERT ||--o{ INCIDENT_NOTE : logs

  ESTATE { uuid id; uuid organization_id FK; string name; string address; string city; json sms_fallback_config }
  ESTATE_MEMBER { uuid id; uuid estate_id FK; uuid user_id FK; uuid unit_id FK; string role "resident|exco|security|manager"; string status "pending|approved|suspended"; uuid approved_by }
  DUES_PLAN { uuid id; uuid estate_id FK; string name; bigint amount; string frequency; bool active }
  ANNOUNCEMENT { uuid id; uuid estate_id FK; string title; text body; string audience; json channels; datetime sent_at }
  GATE_PASS { uuid id; uuid estate_id FK; uuid host_member_id FK; string visitor_name; string visitor_phone; string kind "visitor|artisan|delivery"; string code UK; datetime valid_from; datetime valid_to; int max_uses; int uses; string status }
  PANIC_ALERT { uuid id; uuid estate_id FK; uuid raised_by FK; string kind "robbery|kidnapping|fire|medical|suspicious_person"; bool silent; json location "🔒 consented only"; string status "triggered|acknowledged|responding|resolved|false_alarm|cancelled"; datetime triggered_at; datetime acknowledged_at; datetime resolved_at }
  ALERT_DELIVERY { uuid id; uuid alert_id FK; uuid recipient_id; string channel "ws|push|sms"; string status "queued|sent|delivered|acknowledged|failed"; datetime queued_at; datetime delivered_at; string provider_ref }
  INCIDENT_NOTE { uuid id; uuid alert_id FK; uuid author_id; text note; datetime at }
```

* **Rate limits:** a resident is limited per window. A **false-alarm** status counts toward the
  resident's record, which estate admins can review.
* **Delivery-time metric:** time from `triggered_at` to the first `delivered`/`acknowledged`
  delivery, per channel.

## 7. Platform: notifications and analytics [Phase 1+]

* `NOTIFICATION { id, user_id, channel push|sms|email|whatsapp, template, payload, status,
  provider_ref, sent_at, delivered_at, error }`: one row per message we send, for receipts,
  delivery tracking and cost.
* `ANALYTICS_EVENT { id, name, user_id, organization_id, properties jsonb, occurred_at }`:
  product events. Success metrics are computed from operational tables, not only from events.
