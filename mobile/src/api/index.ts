/**
 * Typed calls to the Homesika backend. Shapes mirror the Django serializers:
 *   auth  -> backend/apps/accounts/{urls,views,serializers}.py
 *   lease/charges -> backend/apps/leasing/{views,serializers}.py (MyLeaseSerializer, ChargeSerializer)
 *   payments -> backend/apps/payments/{views,serializers}.py (PaymentSerializer, TenantPayView, PublicStatusView)
 * Money fields are decimal strings in major units.
 */
import { api } from "@/lib/api";

export type LanguageCode = "en" | "pcm";

export type User = {
  id: string;
  phone_number: string;
  email: string | null;
  first_name: string;
  last_name: string;
  country: string;
  preferred_language: string;
  is_phone_verified: boolean;
  is_email_verified: boolean;
  has_login_pin: boolean;
  has_transaction_pin: boolean;
  created_at: string;
};

export type TokenPair = { access: string; refresh: string };

export type OtpChannel = "sms" | "email";

/** otp.describe(): a one-time code was sent. */
export type Challenge = {
  challenge_id: string;
  purpose: "signup" | "new_device" | "reset_pin";
  channel: OtpChannel;
  destination: string;
  email_fallback: boolean;
  expires_in: number;
  resend_in: number;
};

export type SignedIn = { next: "done"; user: User; tokens: TokenPair; device_secret: string };
export type Verified = { next: "create_pin"; setup_token: string } | SignedIn;

export type RegisterInput = {
  first_name: string;
  last_name: string;
  phone_number: string;
  email?: string;
  preferred_language?: LanguageCode;
  channel?: OtpChannel;
  accept_terms: boolean;
};

/** Cursor pagination (apps/core/pagination.py): `next` is a full URL. */
export type Page<T> = { next: string | null; previous: string | null; results: T[] };

export type LeaseStatus = "active" | "ended" | "terminated";

export type MyLease = {
  id: string;
  /** The unit's id (send as `unit` on an electricity order for my own meter). Older servers may omit it. */
  unit?: string;
  /** Prepaid meter on my unit ("" when the landlord hasn't added one). */
  meter_number?: string;
  /** Electricity company: a name ("Ikeja Electric") or a code; match it with matchDisco(). */
  disco?: string;
  unit_label: string;
  property_name: string;
  property_address: string;
  landlord: string;
  landlord_phone: string;
  start_date: string;
  end_date: string;
  rent_amount: string;
  rent_frequency: "monthly" | "quarterly" | "biannual" | "annual";
  service_charge_amount: string;
  currency: string;
  status: LeaseStatus;
};

export type ChargeStatus = "open" | "part_paid" | "paid" | "waived" | "void";
export type ChargeKind = "rent" | "service_charge" | "deposit" | "dues" | "other";

export type Charge = {
  id: string;
  lease: string | null;
  kind: ChargeKind;
  description: string;
  period_start: string | null;
  period_end: string | null;
  due_date: string;
  amount: string;
  amount_paid: string;
  balance: string;
  currency: string;
  status: ChargeStatus;
  is_overdue: boolean;
  waived_reason: string;
  tenant_name: string;
  unit_label: string;
  property_name: string;
  organization: string;
  organization_name: string;
  created_at: string;
};

export type Payment = {
  id: string;
  tenant: string;
  tenant_name: string;
  gateway: string;
  gateway_reference: string;
  channel: string;
  amount: string;
  unallocated_amount: string;
  currency: string;
  status: "succeeded" | "reversed";
  paid_at: string;
  receipt_number: string | null;
  needs_review: boolean;
  review_reason: string;
  note: string;
  applied_to: { charge: string; description: string; amount: string }[];
};

export type PayStarted = { reference: string; checkout_url: string; gateway: string };
export type PayLinkStatus = "pending" | "paid" | "expired" | "cancelled";
export type PayStatus = { status: PayLinkStatus; receipt_number: string | null };

const anon = { method: "POST" as const, auth: false };

/** `next` from a page is a full URL; the client accepts it as-is. */
const page = <T>(path: string) => api<Page<T>>(path);

export const authApi = {
  register: (input: RegisterInput) => api<Challenge>("/api/v1/auth/register/", { ...anon, body: input }),
  resend: (challenge_id: string, channel?: OtpChannel) =>
    api<Challenge>("/api/v1/auth/otp/resend/", { ...anon, body: channel ? { challenge_id, channel } : { challenge_id } }),
  verify: (challenge_id: string, code: string, device_id: string, device_name: string) =>
    api<Verified>("/api/v1/auth/otp/verify/", { ...anon, body: { challenge_id, code, device_id, device_name } }),
  setupPin: (setup_token: string, pin: string, device_id: string, device_name: string) =>
    api<SignedIn>("/api/v1/auth/pin/setup/", {
      ...anon,
      body: { setup_token, pin, pin_confirm: pin, device_id, device_name },
    }),
  pinLogin: (device_id: string, device_secret: string, pin: string) =>
    api<{ user: User; tokens: TokenPair }>("/api/v1/auth/pin-login/", { ...anon, body: { device_id, device_secret, pin } }),
  /** New / reinstalled phone: phone + PIN, then a code. */
  loginStart: (identifier: string, pin: string) =>
    api<Challenge>("/api/v1/auth/login/", { ...anon, body: { identifier, pin } }),
  forgotPin: (identifier: string) => api<Challenge>("/api/v1/auth/pin/forgot/", { ...anon, body: { identifier } }),
  logout: (refresh: string, device_id: string) =>
    api<void>("/api/v1/auth/logout/", { method: "POST", body: { refresh, device_id } }),
  me: () => api<User>("/api/v1/me/"),
  updateMe: (patch: Partial<Pick<User, "first_name" | "last_name" | "preferred_language">>) =>
    api<User>("/api/v1/me/", { method: "PATCH", body: patch }),
};

export const tenantApi = {
  leases: () => api<MyLease[]>("/api/v1/me/leases/"),
  /** Outstanding by default; `all` adds history. */
  charges: (opts: { all?: boolean; cursor?: string | null } = {}) =>
    page<Charge>(opts.cursor ?? `/api/v1/me/charges/?page_size=100${opts.all ? "&all=1" : ""}`),
  charge: (id: string) => api<Charge>(`/api/v1/me/charges/${encodeURIComponent(id)}/`),
  payments: (cursor?: string | null) => page<Payment>(cursor ?? "/api/v1/me/payments/"),
  receiptPath: (paymentId: string) => `/api/v1/me/payments/${encodeURIComponent(paymentId)}/receipt/`,
  pay: (input: { charges: string[]; amount?: string }, idempotencyKey: string) =>
    api<PayStarted>("/api/v1/me/pay/", { method: "POST", body: input, idempotencyKey }),
  /** Public: verifies with the gateway if still pending. */
  payStatus: (reference: string) =>
    api<PayStatus>(`/api/v1/pay/${encodeURIComponent(reference)}/status/`, { auth: false }),
};

/** All outstanding charges (follows cursors; tenants rarely have more than one page). */
export async function allOutstandingCharges(): Promise<Charge[]> {
  const out: Charge[] = [];
  let cursor: string | null = null;
  for (let i = 0; i < 10; i++) {
    const p: Page<Charge> = await tenantApi.charges({ cursor });
    out.push(...p.results);
    if (!p.next) break;
    cursor = p.next;
  }
  return out;
}

/* ---- Phase 2 -------------------------------------------------------------------------------
 *   assistant -> backend/apps/assistant/{views,serializers}.py (ChatView, ActionView, ReplySerializer)
 *                messages: backend/apps/messaging/serializers.py (MessageSerializer)
 *   whatsapp  -> backend/apps/messaging/views.py (MyWhatsAppView, OptInSerializer)
 *   listings  -> backend/apps/listings/views.py (Public* views; PublicListingSerializer)
 */

export type PendingActionStatus = "proposed" | "executed" | "rejected" | "expired" | "failed";

export type PendingAction = {
  id: string;
  tool: string;
  summary: string;
  status: PendingActionStatus;
  expires_at: string;
};

export type ChatMessage = {
  id: string;
  /** "in" = from the person (me), "out" = to the person (assistant, staff or system). */
  direction: "in" | "out";
  sender: "person" | "assistant" | "staff" | "system";
  kind: string;
  body: string;
  status: string;
  error: string;
  sent_by_name: string | null;
  created_at: string;
};

export type ChatHistory = {
  conversation: string | null;
  messages: ChatMessage[];
  pending_action: PendingAction | null;
  /** A person has been asked to reply (an open escalation). Older servers may omit it. */
  escalated?: boolean;
};

/** POST /assistant/messages/ and POST /assistant/actions/{id}/{confirm|reject}/. */
export type AssistantReply = {
  conversation: string;
  text: string;
  pending_action: PendingAction | null;
  escalated: boolean;
};

/** The backend rejects longer messages (guardrails.MAX_INPUT_CHARS). */
export const MAX_CHAT_CHARS = 2000;

export const assistantApi = {
  history: () => api<ChatHistory>("/api/v1/assistant/messages/?channel=app"),
  /** idempotencyKey: one per message, reused on retry, so the server never stores a message twice. */
  send: (text: string, idempotencyKey: string) =>
    api<AssistantReply>("/api/v1/assistant/messages/", { method: "POST", body: { text, channel: "app" }, idempotencyKey }),
  decide: (actionId: string, decision: "confirm" | "reject") =>
    api<AssistantReply>(`/api/v1/assistant/actions/${encodeURIComponent(actionId)}/${decision}/`, { method: "POST" }),
  clear: () => api<void>("/api/v1/assistant/messages/", { method: "DELETE" }),
};

export type WhatsAppPref = { opted_in: boolean };

export const whatsappApi = {
  get: () => api<WhatsAppPref>("/api/v1/me/whatsapp/"),
  set: (opted_in: boolean) => api<WhatsAppPref>("/api/v1/me/whatsapp/", { method: "PUT", body: { opted_in } }),
};

export type ListingPhoto = { id: string; url: string; caption: string; position: number };
export type ViewingSlot = { id: string; starts_at: string; ends_at: string };

export type PublicListing = {
  ref: string;
  title: string;
  description: string;
  /** JSONField (a list of short strings in practice); render defensively. */
  features: unknown;
  area: string;
  city: string;
  bedrooms: number | null;
  bathrooms: number | null;
  rent_amount: string;
  rent_period: "year" | "month";
  currency: string;
  landlord: string;
  photos: ListingPhoto[];
  published_at: string | null;
};

export type PublicListingDetail = PublicListing & { slots: ViewingSlot[] };

export type ListingFilters = { area?: string; max_rent?: string; bedrooms?: number | null };

export type EnquiryInput = { name: string; phone_number: string; message?: string };

const publicGet = <T>(path: string) => api<T>(path, { auth: false });

export const listingsApi = {
  /** Not paginated: at most 30 published listings, cheapest first. */
  search: (f: ListingFilters = {}) => {
    const q = new URLSearchParams();
    if (f.area?.trim()) q.set("area", f.area.trim());
    if (f.max_rent) q.set("max_rent", f.max_rent);
    if (f.bedrooms) q.set("bedrooms", String(f.bedrooms));
    const qs = q.toString();
    return publicGet<PublicListing[]>(`/api/v1/listings/${qs ? `?${qs}` : ""}`);
  },
  detail: (ref: string) => publicGet<PublicListingDetail>(`/api/v1/listings/${encodeURIComponent(ref)}/`),
  book: (ref: string, input: EnquiryInput & { slot: string }) =>
    api<{ status: "booked"; starts_at: string }>(`/api/v1/listings/${encodeURIComponent(ref)}/book/`, {
      method: "POST",
      auth: false,
      body: input,
    }),
  enquire: (ref: string, input: EnquiryInput) =>
    api<{ status: "received" }>(`/api/v1/listings/${encodeURIComponent(ref)}/enquire/`, { method: "POST", auth: false, body: input }),
};

/** Features as display strings (the API field is free-form JSON). */
export function listingFeatures(features: unknown): string[] {
  if (!Array.isArray(features)) return [];
  return features.filter((f): f is string | number => typeof f === "string" || typeof f === "number").map(String).filter(Boolean);
}

/* ---- Phase 3: bills ---------------------------------------------------------------------------
 *   backend/apps/bills/{views,serializers,services}.py (BillerSerializer, PlanSerializer, OrderSerializer)
 *   Pay per purchase at the gateway checkout; no wallet. Undeliverable orders are refunded automatically.
 */

export type BillCategory = "airtime" | "data" | "cable_tv" | "electricity";

export type BillPlan = {
  id: string;
  code: string;
  name: string;
  /** null = the person chooses the amount (electricity prepaid/postpaid). */
  price: string | null;
  validity_days: number | null;
  data_mb: number | null;
};

export type Biller = {
  id: string;
  category: BillCategory;
  code: string;
  name: string;
  customer_label: string;
  requires_verification: boolean;
  min_amount: string | null;
  max_amount: string | null;
  /** Homesika's fee per order (naira), added to the total. Optional: older servers don't send it. */
  fee?: string;
  plans: BillPlan[];
};

/** POST /bills/verify/: the meter / smartcard owner. `details` varies by provider (e.g. customer_address). */
export type BillCustomer = { customer_id: string; name: string; details: Record<string, unknown> };

export type BillOrderStatus = "awaiting_payment" | "processing" | "delivered" | "refund_pending" | "refunded" | "expired";

export type BillOrder = {
  id: string;
  reference: string;
  category: BillCategory;
  biller: string;
  biller_name: string;
  plan: string | null;
  plan_name: string | null;
  customer_id: string;
  customer_name: string;
  amount: string;
  fee: string;
  total: string;
  currency: string;
  status: BillOrderStatus;
  checkout_url: string;
  /** Electricity token; "" until delivered. */
  token: string;
  units: string;
  receipt_number: string;
  failure_reason: string;
  created_at: string;
  paid_at: string | null;
  delivered_at: string | null;
  refunded_at: string | null;
  expires_at: string;
};

export type BillOrderInput = {
  biller: string;
  plan?: string;
  customer_id: string;
  /** Whole naira as a decimal string ("1500.00"); omitted when the plan has a price. */
  amount?: string;
  /** My unit (electricity for my own meter). */
  unit?: string;
};

export const billsApi = {
  /** Public. Not paginated. */
  catalogue: (category: BillCategory) =>
    publicGet<Biller[]>(`/api/v1/bills/catalogue/?category=${encodeURIComponent(category)}`),
  verify: (input: { biller: string; plan?: string; customer_id: string }) =>
    api<BillCustomer>("/api/v1/bills/verify/", { method: "POST", body: input }),
  /** idempotencyKey: one per submission, reused when retrying the same submission. */
  createOrder: (input: BillOrderInput, idempotencyKey: string) =>
    api<BillOrder>("/api/v1/bills/orders/", { method: "POST", body: input, idempotencyKey }),
  orders: (cursor?: string | null) => page<BillOrder>(cursor ?? "/api/v1/bills/orders/"),
  /** Polling this also asks the gateway whether an unpaid order has been paid. */
  order: (id: string) => api<BillOrder>(`/api/v1/bills/orders/${encodeURIComponent(id)}/`),
  receiptPath: (id: string) => `/api/v1/bills/orders/${encodeURIComponent(id)}/receipt/`,
};

/* ---- Phase 4: repairs and artisans ----------------------------------------------------------------
 *   backend/apps/maintenance/{views,serializers}.py (TicketSerializer viewer=tenant, ArtisanJobSerializer)
 *   backend/apps/artisans/{views,serializers}.py (MyArtisanSerializer)
 *   No money moves here: the price of repair work is agreed with the artisan.
 */

export type Trade =
  | "plumbing"
  | "electrical"
  | "carpentry"
  | "painting"
  | "ac"
  | "generator"
  | "roofing"
  | "tiling"
  | "welding"
  | "appliance"
  | "pest"
  | "cleaning"
  | "locksmith"
  | "other";
export const TRADES: Trade[] = [
  "plumbing",
  "electrical",
  "carpentry",
  "painting",
  "ac",
  "generator",
  "roofing",
  "tiling",
  "welding",
  "appliance",
  "pest",
  "cleaning",
  "locksmith",
  "other",
];
export type TicketStatus = "awaiting_approval" | "approved" | "assigned" | "in_progress" | "done" | "confirmed" | "rejected" | "cancelled";
export type TicketPriority = "low" | "normal" | "urgent" | "emergency";
export type JobStatus = "offered" | "accepted" | "declined" | "on_site" | "completed" | "confirmed" | "cancelled";

export type TicketPhoto = { id: string; stage: "report" | "completion"; url: string | null; created_at: string };
export type TicketEvent = {
  id: string;
  kind: string;
  actor_role: "tenant" | "staff" | "artisan" | "system" | "";
  actor_name: string;
  note: string;
  internal: boolean;
  created_at: string;
};
export type TicketJob = {
  id: string;
  status: JobStatus;
  artisan: {
    id: string;
    display_name: string;
    is_verified: boolean;
    rating_avg: number | null;
    rating_count: number;
    jobs_completed: number;
    /** Only once they've accepted. */
    phone_number: string | null;
  };
  offer_expires_at: string;
  scheduled_for: string | null;
  started_at: string | null;
  completed_at: string | null;
  completion_note: string;
};
/** GET /me/tickets/ and /me/tickets/{id}/ (the tenant's view). */
export type Ticket = {
  id: string;
  reference: string;
  status: TicketStatus;
  category: Trade;
  priority: TicketPriority;
  title: string;
  description: string;
  access_notes: string;
  channel: "app" | "web" | "whatsapp";
  unit: { id: string; label: string; property: string; address: string; city: string; organization: string };
  closed_reason: string;
  done_at: string | null;
  confirmed_at: string | null;
  auto_confirmed: boolean;
  created_at: string;
  photos: TicketPhoto[];
  job: TicketJob | null;
  rating: { score: number; comment: string } | null;
  events: TicketEvent[];
  can: ("cancel" | "confirm" | "reopen" | "rate" | "comment" | "photo")[];
};
export type ReportInput = {
  lease: string;
  category: Trade;
  priority: TicketPriority;
  title: string;
  description: string;
  access_notes?: string;
};

export type CheckStatus = "not_started" | "pending" | "passed" | "failed";
export type VoucherKind = "guarantor" | "reference";
export type MyVoucher = {
  id: string;
  kind: VoucherKind;
  full_name: string;
  phone_number: string;
  relationship: string;
  occupation: string;
  status: "pending" | "confirmed" | "declined" | "expired";
  link_sent_at: string | null;
  sends: number;
  responded_at: string | null;
};
/** GET/PATCH /artisans/me/ */
export type MyArtisan = {
  id: string;
  display_name: string;
  trades: Trade[];
  service_areas: string[];
  address: string;
  city: string;
  state: string;
  bio: string;
  years_experience: number | null;
  is_available: boolean;
  status: "pending" | "verified" | "suspended" | "removed";
  status_reason: string;
  is_verified: boolean;
  verified_at: string | null;
  rating_avg: number | null;
  rating_count: number;
  jobs_completed: number;
  checks: { kind: "id" | "phone" | "address"; status: CheckStatus; note: string; id_type: string; id_number_last4: string; attempts: number }[];
  vouchers: MyVoucher[];
  requirements: {
    id: boolean;
    phone: boolean;
    address: boolean;
    guarantors: number;
    guarantors_needed: number;
    references: number;
    references_needed: number;
    complete: boolean;
  };
};
export type ApplyInput = {
  display_name: string;
  trades: Trade[];
  service_areas: string[];
  address: string;
  city?: string;
  state?: string;
  bio?: string;
  years_experience?: number | null;
  consent: boolean;
};
export type VoucherInput = {
  kind: VoucherKind;
  full_name: string;
  phone_number: string;
  relationship: string;
  occupation?: string;
  address?: string;
};
export const ID_TYPES = ["nin", "drivers_licence", "voters_card", "passport"] as const;
export type IdType = (typeof ID_TYPES)[number];

/** GET /artisans/me/jobs/ (the artisan's view: address and tenant contact only once accepted). */
export type ArtisanJob = {
  id: string;
  status: JobStatus;
  organization: string;
  offer_note: string;
  offer_expires_at: string;
  scheduled_for: string | null;
  started_at: string | null;
  completed_at: string | null;
  completion_note: string;
  confirmed_at: string | null;
  created_at: string;
  ticket: {
    id: string;
    reference: string;
    status: TicketStatus;
    category: Trade;
    priority: TicketPriority;
    title: string;
    description: string;
    access_notes: string;
    photos: TicketPhoto[];
    events: TicketEvent[];
  };
  location: { area: string; state: string; address?: string; property?: string; unit?: string };
  contact: { name: string; phone_number: string } | null;
  rating: { score: number; comment: string } | null;
  can: ("accept" | "decline" | "schedule" | "start" | "complete" | "comment" | "photo")[];
};

const enc = encodeURIComponent;

export const repairsApi = {
  list: (cursor?: string | null) => page<Ticket>(cursor ?? "/api/v1/me/tickets/?status=all"),
  get: (id: string) => api<Ticket>(`/api/v1/me/tickets/${enc(id)}/`),
  report: (input: ReportInput, idempotencyKey: string) =>
    api<Ticket>("/api/v1/me/tickets/", { method: "POST", body: input, idempotencyKey }),
  addPhoto: (id: string, form: FormData) => api<TicketPhoto>(`/api/v1/me/tickets/${enc(id)}/photos/`, { method: "POST", body: form }),
  cancel: (id: string, reason: string) => api<Ticket>(`/api/v1/me/tickets/${enc(id)}/cancel/`, { method: "POST", body: { reason } }),
  confirm: (id: string) => api<Ticket>(`/api/v1/me/tickets/${enc(id)}/confirm/`, { method: "POST" }),
  reopen: (id: string, note: string) => api<Ticket>(`/api/v1/me/tickets/${enc(id)}/reopen/`, { method: "POST", body: { note } }),
  rate: (id: string, score: number, comment: string) =>
    api<Ticket>(`/api/v1/me/tickets/${enc(id)}/rate/`, { method: "POST", body: { score, comment } }),
  comment: (id: string, note: string) => api<TicketEvent>(`/api/v1/me/tickets/${enc(id)}/comments/`, { method: "POST", body: { note } }),
};

export const artisanApi = {
  me: () => api<MyArtisan>("/api/v1/artisans/me/"),
  apply: (input: ApplyInput) => api<MyArtisan>("/api/v1/artisans/apply/", { method: "POST", body: input }),
  update: (patch: Partial<Pick<MyArtisan, "is_available" | "trades" | "service_areas" | "address" | "city" | "state" | "bio">>) =>
    api<MyArtisan>("/api/v1/artisans/me/", { method: "PATCH", body: patch }),
  submitId: (form: FormData) => api<MyArtisan>("/api/v1/artisans/me/verification/id/", { method: "POST", body: form }),
  addVoucher: (input: VoucherInput) => api<MyVoucher>("/api/v1/artisans/me/verification/vouchers/", { method: "POST", body: input }),
  resendVoucher: (id: string) => api<MyVoucher>(`/api/v1/artisans/me/verification/vouchers/${enc(id)}/resend/`, { method: "POST" }),
  removeVoucher: (id: string) => api<void>(`/api/v1/artisans/me/verification/vouchers/${enc(id)}/`, { method: "DELETE" }),
  jobs: (status: "active" | "history", cursor?: string | null) => page<ArtisanJob>(cursor ?? `/api/v1/artisans/me/jobs/?status=${status}`),
  job: (id: string) => api<ArtisanJob>(`/api/v1/artisans/me/jobs/${enc(id)}/`),
  accept: (id: string, scheduled_for: string | null) =>
    api<ArtisanJob>(`/api/v1/artisans/me/jobs/${enc(id)}/accept/`, { method: "POST", body: { scheduled_for } }),
  decline: (id: string, reason: string) => api<ArtisanJob>(`/api/v1/artisans/me/jobs/${enc(id)}/decline/`, { method: "POST", body: { reason } }),
  schedule: (id: string, scheduled_for: string) =>
    api<ArtisanJob>(`/api/v1/artisans/me/jobs/${enc(id)}/schedule/`, { method: "POST", body: { scheduled_for } }),
  start: (id: string) => api<ArtisanJob>(`/api/v1/artisans/me/jobs/${enc(id)}/start/`, { method: "POST" }),
  complete: (id: string, note: string) => api<ArtisanJob>(`/api/v1/artisans/me/jobs/${enc(id)}/complete/`, { method: "POST", body: { note } }),
  addPhoto: (id: string, form: FormData) => api<TicketPhoto>(`/api/v1/artisans/me/jobs/${enc(id)}/photos/`, { method: "POST", body: form }),
  comment: (id: string, note: string) => api<TicketEvent>(`/api/v1/artisans/me/jobs/${enc(id)}/comments/`, { method: "POST", body: { note } }),
};
