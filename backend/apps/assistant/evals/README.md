# Assistant evaluation set

Evaluation items for the Homesika assistant. The spec is `docs/ASSISTANT.md`: §6 has the
scenario fixtures and §7 has the format. Each `.jsonl` line is one item with these keys: `id`,
`role`, `scenario`, `language`, `channel`, `turns`, `expect`, `notes`. Only the last turn is
scored. Every expected fact comes from the §6 fixtures (today is 2026-10-15, Lagos).

## Files

| File | Scenarios | Covers |
|---|---|---|
| `tenant.jsonl` | `tenant_overdue` (Chidi, 106), `tenant_paid_up` (Amina, 35), `tenant_two_landlords` (Tunde, 42) | Balance, charges, receipts, lease; pay links (all owed, or only some charges); cancelled confirmations; two landlords (Sade Homes has no payout account); disputes, payment problems, complaints, emergencies; privacy (other tenants), prompt injection, OTP/PIN, out of scope |
| `landlord.jsonl` | `landlord` (Emeka Obi, 120) | Portfolio, arrears (665,000 total), occupancy and vacancy (Flat 4D), recent payments, leads and viewings, `send_payment_link` confirmations; dashboard-only actions (record payment, waive, end lease, payout account, delete) are refused; Sade Homes data is refused; legal and eviction questions are refused and pointed to a lawyer |
| `staff.jsonl` | `staff_manager` (31), `staff_agent` (34), `staff_accountant` (32), `staff_viewer` (26) | Capability limits. The agent can't see payments or arrears: refuse, with `must_not_call` set to `list_recent_payments`/`get_tenant_account` and the amounts in `must_not_include`. The viewer can't send links: refuse, with `must_not_call` set to `send_payment_link`. The accountant can't manage listings: refuse. Also normal answers and confirmations for the allowed roles |
| `prospect.jsonl` | `prospect` (118) | Listing search (area, price, bedrooms), areas with no match (Abuja, Ajah, Surulere, where invented place names go in `must_not_include`), viewing bookings (`request_viewing` confirm), the taken slot 2026-10-18 11:00, LST-IKJSC with no open slots, how Homesika works (`search_help`), a prospect asking about rent (no tenancy), privacy and prompt injection |

## Counts

| File | Total | answer | confirm | clarify | escalate | emergency | refuse | en | pcm | multi-turn |
|---|---|---|---|---|---|---|---|---|---|---|
| tenant | 183 | 86 | 17 | 13 | 25 | 10 | 32 | 112 | 71 (39%) | 18 |
| landlord | 120 | 60 | 10 | 5 | 12 | 4 | 29 | 72 | 48 (40%) | 10 |
| staff | 123 | 56 | 9 | 6 | 12 | 6 | 34 | 73 | 50 (41%) | 14 |
| prospect | 118 | 59 | 11 | 9 | 12 | 4 | 23 | 70 | 48 (41%) | 12 |

Escalation reasons (excluding emergency):

| File | dispute | payment_problem | complaint | user_request | low_confidence |
|---|---|---|---|---|---|
| tenant | 5 | 5 | 5 | 6 | 4 |
| landlord | 2 | 3 | 2 | 3 | 2 |
| staff | 2 | 2 | 2 | 4 | 2 |
| prospect | 2 | 2 | 3 | 3 | 2 |

## Conventions

* `confirm` items have `confirmation: true` and an action tool in `tools_any`. The scored turn
  must create a pending action and must not claim the action is done.
* `escalate` and `emergency` items have `tools_any: ["escalate_to_human"]` and the reason in
  `escalation`. Emergency items also have `must_include_any: ["112"]`.
* Amounts are written `440,000`. Dates are given as a list of alternatives
  (`2026-11-01`, `1 November`, `Nov 1`, …).
* Some items have `behaviour: "answer"` with `confirmation: false` and the action tool in
  `must_not_call`. These cover cancellations ("no, cancel it"), the taken slot and the listing
  with no open slots.

## Running

```
python manage.py assistant_eval --role tenant
python manage.py assistant_eval --role landlord
python manage.py assistant_eval --role staff
python manage.py assistant_eval --role prospect
```

(The runner is being built separately; the command is as specified in `docs/ASSISTANT.md` §7.)

## Review needed

* **Pidgin items (`language: "pcm"`) need review by a native speaker** before the set is
  final. Check that each one reads naturally and that the expected reply language is right.
* We wrote more than 110 items per file so that at least 100 remain after review drops items.
* The `notes` field on each item records the judgement calls (for example the clarify vs answer
  items).
