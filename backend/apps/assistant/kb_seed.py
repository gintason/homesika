"""Platform-wide help articles (English and Pidgin). Loaded by migration 0002 and `manage.py seed_kb`.
Edit in the admin afterwards; the Pidgin text needs a native speaker's review."""

ARTICLES = [
    (
        "pay-rent",
        ["tenant"],
        {
            "en": (
                "How to pay rent on Homesika",
                "Your landlord or agent sends you a payment link by WhatsApp or SMS, or you tap Pay in the Homesika app. "
                "The link opens a secure checkout (Paystack or Flutterwave) where you can pay by card, bank transfer or USSD. "
                "The money goes straight to your landlord's bank account; Homesika does not hold it. Your receipt is sent "
                "automatically as soon as the payment is confirmed. Payment links expire after 3 days; ask for a new one if yours has.",
            ),
            "pcm": (
                "How to pay rent for Homesika",
                "Your landlord or agent go send you payment link for WhatsApp or SMS, or you fit press Pay for Homesika app. "
                "The link go open safe checkout (Paystack or Flutterwave) wey you fit pay with card, bank transfer or USSD. "
                "The money go straight enter your landlord bank account; Homesika no dey hold am. Your receipt go come by itself "
                "once dem confirm the payment. Payment link dey expire after 3 days; ask for new one if your own don expire.",
            ),
        },
    ),
    (
        "receipts",
        ["tenant"],
        {
            "en": (
                "Receipts",
                "Every payment recorded on Homesika gets a numbered receipt (for example RCT-000123). It is sent to you by "
                "WhatsApp or SMS with a link to the PDF, and you can always find it in the Payments tab of the app. Cash or "
                "transfer payments made directly to your landlord get a receipt once your landlord records them.",
            ),
            "pcm": (
                "Receipt",
                "Every payment wey dem record for Homesika get receipt with number (like RCT-000123). Dem go send am give you "
                "for WhatsApp or SMS with link to the PDF, and you fit always see am for Payments for the app. If you pay cash "
                "or transfer direct to your landlord, receipt go come once your landlord record am.",
            ),
        },
    ),
    (
        "paid-not-showing",
        ["tenant"],
        {
            "en": (
                "I paid but it isn't showing",
                "Most payments show within a few minutes. If you were debited and it still isn't showing after 30 minutes, "
                "don't pay again: keep your bank's debit alert or transaction reference, and ask for a person here. We check "
                "every payment with the payment company, and missed confirmations are picked up automatically every 15 minutes. "
                "Never share your card PIN, OTP or password with anyone, including Homesika staff.",
            ),
            "pcm": (
                "I don pay but e no show",
                "Most payment dey show inside few minutes. If dem don remove the money and e never show after 30 minutes, no pay "
                "again: keep your bank debit alert or transaction reference, and ask for person here. We dey check every payment "
                "with the payment company, and we dey catch payment wey never show every 15 minutes. No ever give anybody your "
                "card PIN, OTP or password, even Homesika staff.",
            ),
        },
    ),
    (
        "fees",
        [],
        {
            "en": (
                "Fees",
                "The amount on your payment link is the amount of rent or charges you owe. If the checkout adds a fee, it is shown "
                "on the checkout page before you confirm. Homesika never asks you to send money to a personal account.",
            ),
            "pcm": (
                "Charges and fees",
                "The amount wey dey your payment link na the rent or charge wey you owe. If checkout add any fee, e go show for "
                "the checkout page before you confirm. Homesika no go ever tell you make you send money to anybody personal account.",
            ),
        },
    ),
    (
        "whatsapp-messages",
        [],
        {
            "en": (
                "WhatsApp messages: turning them on or off",
                "Homesika sends rent reminders, receipts and replies on WhatsApp to people who have messaged us or switched it on "
                "in the app. Reply STOP to stop reminders and receipts on WhatsApp (you will get them by SMS instead), and START "
                "to turn them back on. You can also change this in the app under Profile.",
            ),
            "pcm": (
                "WhatsApp message: how to on am or off am",
                "Homesika dey send rent reminder, receipt and reply for WhatsApp give people wey don message us or on am for the "
                "app. Reply STOP make reminder and receipt stop for WhatsApp (dem go come by SMS instead), and START to on am back. "
                "You fit also change am for the app under Profile.",
            ),
        },
    ),
    (
        "privacy",
        [],
        {
            "en": (
                "Your data and privacy",
                "Homesika follows Nigeria's Data Protection Act (NDPA). Your landlord sees your tenancy and payment records; other "
                "tenants never see your details. Sensitive details such as ID numbers are encrypted. You can ask for a copy of "
                "your data, or for your account and data to be deleted, in the app under Profile > Privacy.",
            ),
            "pcm": (
                "Your data and privacy",
                "Homesika dey follow Nigeria Data Protection Act (NDPA). Your landlord dey see your tenancy and payment record; "
                "other tenant no go ever see your details. Important details like ID number dey locked (encrypted). You fit ask "
                "for copy of your data, or make dem delete your account and data, for the app under Profile > Privacy.",
            ),
        },
    ),
    (
        "reminders",
        ["tenant", "landlord", "staff"],
        {
            "en": (
                "Rent reminders",
                "Tenants get a reminder 7 days and 1 day before rent is due, on the due day, and 3, 7, 14 and 30 days after if it is "
                "still unpaid. Each reminder includes a payment link when the landlord has set up online payment. Landlords can "
                "turn reminders off in Settings > Organization.",
            ),
            "pcm": (
                "Rent reminder",
                "Tenant dey get reminder 7 days and 1 day before rent due, for the day wey e due, and 3, 7, 14 and 30 days after "
                "if dem never pay. Every reminder get payment link if the landlord don set up online payment. Landlord fit off "
                "reminder for Settings > Organization.",
            ),
        },
    ),
    (
        "landlord-getting-started",
        ["landlord", "staff"],
        {
            "en": (
                "Getting started as a landlord or agent",
                "In the Homesika dashboard: 1) add your properties and units; 2) add tenants with their phone numbers; 3) create "
                "and activate each lease (rent, frequency and dates), which creates the rent schedule; 4) add your payout bank "
                "account in Settings so tenants can pay online straight to you; 5) send payment links and let reminders run. "
                "Record cash or transfers you receive directly under Payments. Recording payments, waiving charges and changing "
                "bank details are done in the dashboard, not in chat.",
            ),
            "pcm": (
                "How landlord or agent go start",
                "For Homesika dashboard: 1) add your property and units; 2) add tenant with their phone number; 3) create and "
                "activate each lease (rent, how often, and dates), e go create the rent schedule; 4) add your payout bank account "
                "for Settings so tenant fit pay online straight to you; 5) send payment link and make reminder dey run. Record "
                "cash or transfer wey you collect direct under Payments. To record payment, cancel charge or change bank details, "
                "use the dashboard, no be chat.",
            ),
        },
    ),
    (
        "viewings",
        ["prospect", "tenant"],
        {
            "en": (
                "Booking a viewing",
                "Ask about any listing and choose one of the open viewing times. When the booking is confirmed you get the address "
                "and the agent's contact. Viewings are free. If you can't make it, reply here so the agent can give the slot to "
                "someone else. Never pay an inspection fee or deposit to a personal account before seeing a property.",
            ),
            "pcm": (
                "How to book viewing (inspection)",
                "Ask about any house wey you like and pick one of the viewing time wey dey open. Once the booking confirm, you go "
                "get the address and the agent contact. Viewing na free. If you no fit come, reply here make the agent give the "
                "time to another person. No ever pay inspection fee or deposit enter anybody personal account before you see the house.",
            ),
        },
    ),
    (
        "about-homesika",
        [],
        {
            "en": (
                "What Homesika is",
                "Homesika (by Homesika Real Estate) helps landlords, agents and tenants in Nigeria: rent schedules, online rent "
                "payment straight to the landlord, automatic receipts and reminders, and rental listings with viewing booking. "
                "You can use it on WhatsApp, in the Homesika app, or on the web dashboard.",
            ),
            "pcm": (
                "Wetin be Homesika",
                "Homesika (from Homesika Real Estate) dey help landlord, agent and tenant for Nigeria: rent schedule, online rent "
                "payment wey go straight to landlord, receipt and reminder wey dey come by itself, and house listing with viewing "
                "booking. You fit use am for WhatsApp, for Homesika app, or for the web dashboard.",
            ),
        },
    ),
    (
        "safety-scams",
        [],
        {
            "en": (
                "Staying safe from scams",
                "Homesika will never ask for your PIN, OTP or password. Pay only through Homesika payment links or the app, which "
                "open Paystack or Flutterwave checkout pages. Be careful of anyone asking you to pay rent, inspection fees or "
                "deposits into a personal account. If something feels wrong, ask for a person here before paying.",
            ),
            "pcm": (
                "How to dodge scam",
                "Homesika no go ever ask for your PIN, OTP or password. Pay only through Homesika payment link or the app, wey dey "
                "open Paystack or Flutterwave checkout. Shine your eye for anybody wey tell you make you pay rent, inspection fee "
                "or deposit enter personal account. If something no clear, ask for person here before you pay.",
            ),
        },
    ),
    (
        "talk-to-a-person",
        [],
        {
            "en": (
                "Talking to a person",
                "You can ask for a person at any time. Your message goes to your landlord's team (for tenants) or to Homesika "
                "support, who reply in this same chat, usually Monday to Saturday, 8am to 6pm Lagos time. In an emergency, call "
                "112 first.",
            ),
            "pcm": (
                "How to talk to person",
                "You fit ask for person anytime. Your message go reach your landlord team (if you be tenant) or Homesika support, "
                "wey go reply for this same chat, normally Monday to Saturday, 8am to 6pm Lagos time. If na emergency, call 112 first.",
            ),
        },
    ),
]

ARTICLES += [
    (
        "repairs",
        ["tenant", "landlord", "staff"],
        {
            "en": (
                "Reporting a repair",
                "Tenants report a repair in the Homesika app (Repairs, then Report a problem) or by telling the assistant on "
                "WhatsApp. Add photos in the app so the artisan comes prepared. Your landlord or their manager approves the "
                "request, then assigns a Verified artisan. You get an update by WhatsApp or SMS at each step: approved, artisan "
                "assigned (with the visit time), and marked fixed. When the work is done, confirm it in the app or tell us it "
                "isn't fixed; if you don't answer within 7 days it is confirmed automatically. You can then rate the artisan. "
                "Homesika doesn't take payment for repair work. If there is danger (fire, gas, sparking wires, flooding), get "
                "safe and call 112 first.",
            ),
            "pcm": (
                "How to report repair",
                "Tenant fit report repair for Homesika app (Repairs, then Report a problem) or tell the assistant for WhatsApp. "
                "Add picture for the app make the artisan come prepare. Your landlord or im manager go approve am, then dem go "
                "assign Verified artisan. You go dey get update for WhatsApp or SMS for every step: approved, artisan don "
                "assign (with the time wey e go come), and e don fix. When work finish, confirm am for the app or tell us say e "
                "never fix; if you no answer inside 7 days, e go confirm by itself. After that you fit rate the artisan. "
                "Homesika no dey collect money for repair work. If danger dey (fire, gas, wire dey spark, flood), comot for "
                "danger and call 112 first.",
            ),
        },
    ),
    (
        "verified-artisans",
        [],
        {
            "en": (
                "What 'Verified artisan' means",
                "An artisan gets the Verified badge only after all of these checks pass: an ID check, their phone number "
                "(confirmed by a code), their address (confirmed by Homesika), two guarantors who confirm by SMS link, and one "
                "reference such as a past client or landlord. Homesika can suspend an artisan after complaints, which removes "
                "the badge. Artisans sign up in the Homesika app (Work as an artisan).",
            ),
            "pcm": (
                "Wetin 'Verified artisan' mean",
                "Artisan go get Verified badge only after all these checks pass: ID check, im phone number (dem confirm am with "
                "code), im address (Homesika confirm am), two guarantors wey confirm with SMS link, and one reference like "
                "person wey e don work for before or landlord. Homesika fit suspend artisan if complaint plenty, and the badge "
                "go comot. Artisan dey register for Homesika app (Work as an artisan).",
            ),
        },
    ),
]


def seed(KbArticle) -> int:
    n = 0
    for slug, audience, langs in ARTICLES:
        for lang, (title, body) in langs.items():
            KbArticle.objects.update_or_create(
                organization=None,
                slug=slug,
                language=lang,
                defaults={"title": title, "body": body, "audience": audience, "status": "published"},
            )
            n += 1
    return n
