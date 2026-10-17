/**
 * Homesika privacy notice (NDPA 2023). DRAFT: have a Nigerian data-protection lawyer review it, and fill
 * in the company registration number, address and data-protection contact before launch.
 * Keep docs/PRIVACY_NOTICE.md in step with this file.
 */
export const NOTICE_VERSION = "2026-10-17 (draft)";

export const SECTIONS: { title: string; body: string[] }[] = [
  {
    title: "Who we are",
    body: [
      "Homesika is run by Homesika Real Estate (registration number and address: to be added before launch). We decide how your personal data is used (we are the data controller). Contact our data-protection team at privacy@homesika (address to be confirmed).",
    ],
  },
  {
    title: "What we collect",
    body: [
      "Your name, phone number, email (if you give it), language and the device you sign in on.",
      "For tenants: your tenancy, rent, charges, payments and receipts, as recorded by your landlord or agent; repair requests and their photos; bills you buy.", "For estate residents: your house, membership, dues and payments; gate passes you make (your visitors' names and, if you give them, phone numbers); emergency alerts you raise and how each alert reached people.",
      "For landlords and agents: your organization, properties, units, team and payout account (bank details are encrypted and only the last 4 digits are shown).",
      "For artisans: your trades and work areas, address (encrypted), NIN and date of birth (encrypted), a photo of your NIN slip or card and, if needed, a proof of address; your guarantors' and references' names, phone numbers and answers.",
      "Messages you send to the Homesika assistant in the app or on WhatsApp.", "If you invite friends or join with a code: who invited whom, and the free service fees you have and use.", "If you send airtime abroad: the recipient's phone number and country.",
      "We collect your location only if you turn on \"Share my location\" for panic alerts, and only at the moment you raise an alert. It is stored encrypted and shown only to your estate's security and managers.", "If you allow notifications, your phone's push notification token, so we can send you alerts and updates.",
    ],
  },
  {
    title: "Why we use it",
    body: [
      "To run your account and the services you use: rent collection and receipts, bills, repairs, messages and the assistant (the contract with you).",
      "To check artisans before landlords let them into homes, and to keep a record of payments (your consent, our legitimate interest in safety, and legal obligations).",
      "To prevent fraud and keep the service secure (legitimate interest).",
      "We don't sell your data and we don't use it for advertising.",
    ],
  },
  {
    title: "Automated checks and AI",
    body: [
      "Artisan checks are automated: your NIN is looked up with a licensed verification service, and the photos of your NIN document and proof of address are read by AI (Anthropic's Claude). Fixed rules then compare the results with what you entered. The AI only reads; it does not compare faces or decide on its own.",
      "If an automatic check says no, you can ask for a person at Homesika to review it, in the app.",
      "The Homesika assistant uses Claude to answer questions from your own records and our help articles. It can't move money; anything it proposes needs your YES.",
    ],
  },
  {
    title: "Who we share it with",
    body: [
      "Your landlord, agent or estate sees what relates to your tenancy, dues and repairs. Other tenants never see your details. Artisans see a repair's address and your first name and phone only after they accept the job.",
      "Service providers who process data for us under contract (data processors):",
      "• Anthropic (Claude AI: the assistant, listing drafts, reading artisan documents), United States.",
      "• Smile ID (NIN verification), and the identity authorities it queries.",
      "• Paystack and Flutterwave (payments and refunds).",
      "• VTU.ng and Flutterwave (airtime, data, TV and electricity), and Reloadly (airtime to phones abroad: the recipient's number), United States.",
      "• Termii (SMS), Meta (WhatsApp messages) and Expo (push notifications to the app, passed on to Google and Apple), United States.",
      "• Our hosting and storage providers (Render; Cloudflare R2 or AWS S3), and Sentry for error reports (no personal data is sent to it).",
      "Some of these process data outside Nigeria. We only use providers who protect it to the standard the NDPA requires, under written agreements.",
      "We share data with authorities only when the law requires it.",
    ],
  },
  {
    title: "How long we keep it",
    body: [
      "Payment records and receipts: as long as the law requires for financial records.",
      "Artisan ID and proof-of-address photos: deleted 90 days after the check passes (we keep the result, the ID type and the last 4 digits).",
      "Repair photos: kept with the repair record while your tenancy or account is active.", "Emergency alerts and their incident log: kept as a safety record by the estate; the location is erased 90 days after the alert closes. Gate passes: kept for the estate's gate log; the visitor's phone number is erased 90 days after the pass ends.", "Messages we send you (SMS, WhatsApp, push): deleted after 180 days.",
      "Assistant messages: kept so the conversation works and for quality; you can clear them in the app.",
      "When you delete your account we delete or anonymise your data, except records we must keep by law.",
    ],
  },
  {
    title: "Your rights",
    body: [
      "You can ask to see, correct or delete your data, ask us to stop or limit using it, take a copy, withdraw consent, and object to decisions made only by automated means. Use Profile in the app or contact us.",
      "You can also complain to the Nigeria Data Protection Commission (NDPC).",
    ],
  },
  {
    title: "Security",
    body: [
      "Sensitive details (ID numbers, bank details, addresses, guarantor details) are encrypted. Private photos are stored separately and only shown through links that expire after 15 minutes. Access to staff tools is limited by role and logged.",
    ],
  },
  {
    title: "Changes",
    body: ["We'll tell you in the app before an important change to this notice takes effect."],
  },
];
