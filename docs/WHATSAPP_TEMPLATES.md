# WhatsApp message templates

WhatsApp only lets a business start a conversation, or write more than 24 hours after the person's
last message, with a **pre-approved template**.

Homesika uses templates for receipts, reminders and payment links. Until a template is approved and
listed in `WHATSAPP_TEMPLATES`, that message goes by **SMS** instead, so nothing breaks while you
wait for approval.

Replies to people who have just written to us (the assistant, and staff replies in the inbox) are
normal messages and need no template.

## Submit these in Meta Business Manager

Go to **WhatsApp Manager → Message templates → Create template**.
* **Category:** Utility.
* **Language:** English.
* **Name:** use the names below exactly.
* The `{{n}}` placeholders must stay in this order, because the code fills them in this order.

| Name | Used for | Body text | Placeholders, in order |
|---|---|---|---|
| `payment_receipt` | The tenant's receipt (`receipt`) | `Payment of {{1}} received by {{2}}. Receipt {{3}}: {{4}}` | amount, landlord, receipt number, receipt link |
| `payment_received` | The landlord's alert (`payment_received`) | `Homesika: {{1}} paid {{2}}. Receipt {{3}}.` | tenant name, amount, receipt number |
| `rent_reminder` | 7 days and 1 day before, and on the due day (`rent_reminder`) | `Hi {{1}}, your rent of {{2}} is due on {{3}}. Pay: {{4}} - {{5}}` | first name, amount, due date, pay link (or "please contact your landlord to pay"), landlord |
| `rent_overdue` | 3, 7, 14 and 30 days late (`rent_overdue`) | `Hi {{1}}, your rent of {{2}} was due on {{3}} and is now overdue. Pay: {{4}} - {{5}}` | same as `rent_reminder` |
| `bill_token` | Electricity token delivered (`bill_token`) | `Homesika: {{1}} token for meter {{2}}: {{3}} ({{4}}). Paid {{5}}. Receipt {{6}}` | DisCo, meter, token, units, amount, receipt number |
| `bill_delivered` | Airtime/data/TV delivered (`bill_delivered`) | `Homesika: {{1}} delivered. Paid {{2}}. Receipt {{3}}` | what, amount, receipt number |
| `bill_refunded` | A bill that couldn't be delivered (`bill_refunded`) | `Homesika: we couldn't deliver {{1}}, so {{2}} is being refunded to the card or account you paid with (usually 1-5 working days).` | what, amount |
| `ticket_update` | Repair status for the tenant: approved, artisan assigned, fixed (`ticket_update`) | `Homesika: your repair request {{1}} ({{2}}): {{3}} {{4}}` | reference, title, what happened, extra (visit time or reason; "-" when none) |
| `job_offer` | A new job for an artisan (`job_offer`) | `Homesika: new job {{1}} from {{2}}: {{3}}. Open the app to accept within {{4}} hours.` | reference, landlord, title, hours |
| `dues_reminder` | Estate dues: 3 days before, on the day, 7 and 30 days late (`dues_reminder`) | `{{1}}: your {{2}} of {{3}} {{4}}. Pay: {{5}}` | estate, dues description, amount, when ("is due on 01 Nov" / "is due today" / "is overdue"), pay link ("-" if the estate has no payout account) |
| `payment_link` | A link sent by staff, or by the assistant on staff request (`payment_link`) | `Hi {{1}}, {{3}} sent you a payment link for {{2}}: {{4}}` | first name, amount, landlord, pay link |

> `TODO(verify)`: Meta's current rules for placeholder position (some versions reject a placeholder
> at the very start or end of the body) and for URLs in the body. If Meta rejects a body, adjust the
> wording around the placeholders but keep their meaning and order. Pidgin templates can follow once
> the English ones are approved; check which language code Meta accepts for Nigerian Pidgin.

## Turn them on

When a template shows **Approved**, add it to `WHATSAPP_TEMPLATES`. In Render, set it in the
`homesika-staging-shared` group. For example:

```json
{"receipt": {"name": "payment_receipt", "language": "en"},
 "payment_received": {"name": "payment_received", "language": "en"},
 "rent_reminder": {"name": "rent_reminder", "language": "en"},
 "rent_overdue": {"name": "rent_overdue", "language": "en"},
 "payment_link": {"name": "payment_link", "language": "en"}}
```

## Delivery rules (built in)

* WhatsApp is used only for people who have **opted in**:
  * they messaged the Homesika number (STOP opts out, START opts back in); or
  * they switched it on in the app (Profile → WhatsApp).
* If WhatsApp reports a message as **failed**, the same text goes out **by SMS**, once.
