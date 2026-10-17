/** Shapes returned by the Homesika API (docs/openapi.yaml + backend serializers). Money is a decimal string. */

export type Money = string;
export type ISODate = string; // YYYY-MM-DD
export type ISODateTime = string;

export interface Paginated<T> {
  next: string | null;
  previous: string | null;
  results: T[];
}

// ---- Auth ----
export interface User {
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
  created_at: ISODateTime;
}

export interface AuthTokens {
  access: string;
  refresh: string;
}

export interface OtpChallenge {
  challenge_id: string;
  purpose: "signup" | "new_device" | "reset_pin" | string;
  channel: "sms" | "email";
  destination: string;
  email_fallback: boolean;
  expires_in: number;
  resend_in: number;
}

export interface SignedIn {
  next?: "done";
  user: User;
  tokens: AuthTokens;
  device_secret?: string;
}

export interface SetupNeeded {
  next: "create_pin";
  setup_token: string;
}

// ---- Orgs ----
export type Role = "owner" | "manager" | "agent" | "accountant" | "estate_admin" | "security" | "viewer";
export type OrgKind = "landlord" | "agency" | "estate" | "platform";

export interface Organization {
  id: string;
  name: string;
  kind: OrgKind;
  country: string;
  currency: string;
  timezone: string;
  phone_number: string;
  email: string;
  address: string;
  rent_reminders_enabled: boolean;
  my_role: Role | null;
  created_at: ISODateTime;
}

export interface Membership {
  id: string;
  name: string;
  phone_number: string;
  role: Role;
  status: "active" | "invited" | "removed";
  created_at: ISODateTime;
}

// ---- Properties ----
export type PropertyKind = "block" | "house" | "compound" | "commercial" | "mixed" | "other";
export interface Property {
  id: string;
  name: string;
  kind: PropertyKind;
  address: string;
  city: string;
  state: string;
  country: string;
  notes: string;
  is_archived: boolean;
  unit_count: number;
  occupied_count: number;
  created_at: ISODateTime;
}

export type UnitKind = "flat" | "room" | "house" | "shop" | "office" | "other";
export type UnitStatus = "vacant" | "occupied" | "unavailable";
export interface Unit {
  id: string;
  property: string;
  property_name: string;
  label: string;
  kind: UnitKind;
  bedrooms: number | null;
  default_rent_amount: Money | null;
  status: UnitStatus;
  meter_number: string;
  disco: string;
  created_at: ISODateTime;
}

// ---- Leasing ----
export interface Tenant {
  id: string;
  full_name: string;
  phone_number: string;
  email: string;
  occupation: string;
  next_of_kin: string;
  id_document: string;
  notes: string;
  has_app: boolean;
  active_lease: { id: string; unit: string; property: string } | null;
  created_at: ISODateTime;
}

export type RentFrequency = "monthly" | "quarterly" | "biannual" | "annual";
export type LeaseStatus = "draft" | "active" | "ended" | "terminated";
export interface Lease {
  id: string;
  unit: string;
  unit_label: string;
  property_name: string;
  tenant: string;
  tenant_name: string;
  start_date: ISODate;
  end_date: ISODate;
  rent_amount: Money;
  rent_frequency: RentFrequency;
  service_charge_amount: Money;
  deposit_amount: Money;
  currency: string;
  status: LeaseStatus;
  ended_on: ISODate | null;
  notes: string;
  balance: Money | null;
  created_at: ISODateTime;
}

export type ChargeKind = "rent" | "service_charge" | "deposit" | "dues" | "other";
export type ChargeStatus = "open" | "part_paid" | "paid" | "waived" | "void";
export interface Charge {
  id: string;
  lease: string;
  kind: ChargeKind;
  description: string;
  period_start: ISODate | null;
  period_end: ISODate | null;
  due_date: ISODate;
  amount: Money;
  amount_paid: Money;
  balance: Money;
  currency: string;
  status: ChargeStatus;
  is_overdue: boolean;
  waived_reason: string;
  tenant_name: string;
  unit_label: string;
  property_name: string;
  created_at: ISODateTime;
}

export interface Dashboard {
  overdue_amount: Money;
  overdue_charges: number;
  due_next_30_days: Money;
  units: number;
  occupied_units: number;
  currency: string;
}

export interface ArrearsRow {
  lease: string;
  tenant: string;
  tenant_name: string;
  tenant_phone: string;
  unit: string;
  property: string;
  owed: Money;
  charges: number;
  oldest_due: ISODate;
  days_overdue: number;
}

export interface Arrears {
  currency: string;
  total_owed: Money;
  results: ArrearsRow[];
}

// ---- Payments ----
export type PaymentChannel = "cash" | "bank_transfer" | "pos" | "cheque";
export interface Payment {
  id: string;
  tenant: string;
  tenant_name: string;
  gateway: "paystack" | "flutterwave" | "mock" | "manual";
  gateway_reference: string;
  channel: string;
  amount: Money;
  unallocated_amount: Money;
  currency: string;
  status: "succeeded" | "reversed";
  paid_at: ISODateTime;
  receipt_number: string | null;
  needs_review: boolean;
  review_reason: string;
  note: string;
  applied_to: Array<{ charge: string; description: string; amount: Money }>;
}

export type LinkStatus = "pending" | "paid" | "expired" | "cancelled";
export interface PaymentLink {
  id: string;
  reference: string;
  tenant: string;
  tenant_name: string;
  charges: string[];
  amount: Money;
  currency: string;
  description: string;
  status: LinkStatus;
  expires_at: ISODateTime;
  gateway: string;
  url: string;
  created_at: ISODateTime;
}

export interface SettlementAccount {
  id: string;
  gateway: string;
  bank_code: string;
  bank_name: string;
  account_last4: string;
  account_name: string;
  status: "active" | "failed" | "disabled";
  failure_reason: string;
  created_at: ISODateTime;
}

// ---- Accounting ----
export type ExpenseCategory =
  | "repairs"
  | "utilities"
  | "cleaning"
  | "security"
  | "agent_fee"
  | "legal"
  | "tax"
  | "insurance"
  | "other";
export interface Expense {
  id: string;
  property: string | null;
  property_name: string | null;
  unit: string | null;
  category: ExpenseCategory;
  amount: Money;
  currency: string;
  spent_on: ISODate;
  vendor: string;
  description: string;
  created_at: ISODateTime;
}

export interface StatementTotals {
  billed: Money;
  collected: Money;
  unallocated: Money;
  expenses: Money;
  net: Money;
  outstanding_now: Money;
}
export interface Statement {
  period: { start: ISODate; end: ISODate };
  currency: string;
  totals: StatementTotals;
  by_property: Array<{ property: string | null; billed: Money; collected: Money; expenses: Money; net: Money }>;
  expenses_by_category: Record<string, Money>;
  collections: Array<{
    date: ISODate;
    tenant: string;
    property: string;
    unit: string;
    for: string;
    channel: string;
    receipt: string;
    amount: Money;
  }>;
  expense_lines: Array<{
    date: ISODate;
    category: string;
    property: string;
    vendor: string;
    description: string;
    amount: Money;
  }>;
}

// ---- Public pay page ----
export interface PublicLink {
  reference: string;
  landlord: string;
  tenant_first_name: string;
  description: string;
  amount: Money;
  currency: string;
  status: LinkStatus;
  expires_at: ISODateTime;
  items: Array<{ description: string; due_date: ISODate; unit: string }>;
  receipt_number: string | null;
  mock: boolean;
}

export interface PublicStatus {
  status: LinkStatus;
  receipt_number: string | null;
}

// ---- Bill payments (Phase 3) ----
export type BillStatus = "awaiting_payment" | "processing" | "delivered" | "refund_pending" | "refunded" | "expired";

/** Public GET /bills/{reference}/status/. The token/PIN is never returned here: it goes by SMS/WhatsApp and to the app. */
export interface PublicBillStatus {
  status: BillStatus;
  receipt_number: string | null;
}

// ---- Listings (Phase 2) ----
export type ListingStatus = "draft" | "published" | "let" | "archived";
export type RentPeriod = "year" | "month";
export interface ListingPhoto {
  id: string;
  url: string;
  caption: string;
  position: number;
}
export interface Listing {
  id: string;
  ref: string;
  unit: string | null;
  title: string;
  description: string;
  whatsapp_caption: string;
  features: string[];
  area: string;
  city: string;
  address: string;
  bedrooms: number | null;
  bathrooms: number | null;
  rent_amount: Money;
  rent_period: RentPeriod;
  currency: string;
  status: ListingStatus;
  published_at: ISODateTime | null;
  ai_generated: boolean;
  contact_phone: string;
  photos: ListingPhoto[];
  lead_count: number;
  created_at: ISODateTime;
}

/** POST listings/generate/ response: a draft for the agent to check. */
export interface ListingDraft {
  title: string;
  description: string;
  whatsapp_caption: string;
  features: string[];
  suggested_replies: Array<{ question: string; answer: string }>;
  model?: string;
}

export interface ViewingSlot {
  id: string;
  listing: string;
  starts_at: ISODateTime;
  ends_at: ISODateTime;
  capacity: number;
  agent: string | null;
  booked: number;
}

export type LeadStage = "new" | "contacted" | "viewing_booked" | "viewed" | "applied" | "won" | "lost";
export type ViewingStatus = "booked" | "done" | "no_show" | "cancelled";
export interface Viewing {
  id: string;
  lead: string;
  lead_name: string;
  lead_phone: string;
  listing: string;
  listing_title: string;
  slot: string;
  starts_at: ISODateTime;
  status: ViewingStatus;
  notes: string;
}
export interface Lead {
  id: string;
  listing: string | null;
  listing_title: string | null;
  name: string;
  phone_number: string;
  source: "whatsapp" | "web" | "app" | "manual";
  stage: LeadStage;
  message: string;
  notes: string;
  assigned_to: string | null;
  viewings: Viewing[];
  created_at: ISODateTime;
}

export interface PublicListing {
  ref: string;
  title: string;
  description: string;
  features: string[];
  area: string;
  city: string;
  bedrooms: number | null;
  bathrooms: number | null;
  rent_amount: Money;
  rent_period: RentPeriod;
  currency: string;
  landlord: string;
  photos: ListingPhoto[];
  published_at: ISODateTime | null;
}
/** GET /listings/{ref}/ adds the open viewing slots. */
export interface PublicListingDetail extends PublicListing {
  slots: Array<{ id: string; starts_at: ISODateTime; ends_at: ISODateTime }>;
}

// ---- Inbox (Phase 2) ----
export type ConversationStatus = "bot" | "handoff" | "closed";
export interface InboxMessage {
  id: string;
  direction: "in" | "out";
  sender: "person" | "assistant" | "staff" | "system";
  kind: string;
  body: string;
  status: "received" | "queued" | "sent" | "delivered" | "read" | "failed";
  error: string;
  sent_by_name: string | null;
  created_at: ISODateTime;
}
export type EscalationReason =
  | "dispute"
  | "payment_problem"
  | "emergency"
  | "user_request"
  | "complaint"
  | "low_confidence"
  | "limit"
  | "refusal";
export interface Escalation {
  id: string;
  reason: EscalationReason;
  summary: string;
  status: "open" | "assigned" | "resolved";
  assigned_to: string | null;
  resolved_at: ISODateTime | null;
  created_at: ISODateTime;
}
export interface Conversation {
  id: string;
  channel: "whatsapp" | "app" | "web";
  status: ConversationStatus;
  language: "en" | "pcm";
  contact_name: string;
  contact_phone: string;
  open_escalation: Escalation | null;
  last_message: InboxMessage | null;
  last_inbound_at: ISODateTime | null;
  last_message_at: ISODateTime | null;
  can_reply_freely: boolean;
  handoff_by: string | null;
}
export interface ConversationDetail extends Conversation {
  messages: InboxMessage[];
  escalations: Escalation[];
}

// ---- Assistant + knowledge base (Phase 2) ----
export type KbAudience = "tenant" | "landlord" | "staff" | "prospect";
export interface KbArticle {
  id: string;
  slug: string;
  title: string;
  body: string;
  language: "en" | "pcm";
  audience: KbAudience[];
  status: "draft" | "published";
  updated_at: ISODateTime;
}
export interface PendingAction {
  id: string;
  tool: string;
  summary: string;
  status: "proposed" | "executed" | "rejected" | "expired" | "failed";
  expires_at: ISODateTime;
}
/** POST assistant/messages/ and actions/{id}/confirm|reject/. */
export interface AssistantReply {
  conversation: string;
  text: string;
  pending_action: PendingAction | null;
  escalated: boolean;
}
/** GET assistant/messages/?channel=web */
export interface AssistantHistory {
  conversation: string | null;
  messages: InboxMessage[];
  pending_action: PendingAction | null;
}

// ---- Repairs and artisans (Phase 4) ---------------------------------------------------------------

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
export type TicketStatus =
  | "awaiting_approval"
  | "approved"
  | "assigned"
  | "in_progress"
  | "done"
  | "confirmed"
  | "rejected"
  | "cancelled";
export type TicketPriority = "low" | "normal" | "urgent" | "emergency";
export type JobStatus = "offered" | "accepted" | "declined" | "on_site" | "completed" | "confirmed" | "cancelled";
export type TicketAction =
  | "approve"
  | "reject"
  | "resolve"
  | "assign"
  | "reassign"
  | "confirm"
  | "cancel"
  | "comment"
  | "photo";

export interface TicketPhoto {
  id: string;
  stage: "report" | "completion";
  /** A signed link that works for about 15 minutes. */
  url: string | null;
  created_at: ISODateTime;
}
export interface TicketEvent {
  id: string;
  kind: string;
  actor_role: "tenant" | "staff" | "artisan" | "system" | "";
  actor_name: string;
  note: string;
  internal: boolean;
  created_at: ISODateTime;
}
export interface TicketJob {
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
  offer_expires_at: ISODateTime;
  scheduled_for: ISODateTime | null;
  started_at: ISODateTime | null;
  completed_at: ISODateTime | null;
  completion_note: string;
}
/** GET /orgs/{org}/tickets/ and /{id}/ (staff view). */
export interface Ticket {
  id: string;
  reference: string;
  status: TicketStatus;
  category: Trade;
  priority: TicketPriority;
  title: string;
  description: string;
  access_notes: string;
  channel: "app" | "web" | "whatsapp";
  raised_by_staff: boolean;
  unit: { id: string; label: string; property: string; address: string; city: string; organization: string };
  tenant: { id: string; full_name: string; phone_number: string } | null;
  closed_reason: string;
  approved_at: ISODateTime | null;
  done_at: ISODateTime | null;
  confirmed_at: ISODateTime | null;
  auto_confirmed: boolean;
  created_at: ISODateTime;
  updated_at: ISODateTime;
  photos: TicketPhoto[];
  job: TicketJob | null;
  rating: { score: number; comment: string } | null;
  events: TicketEvent[];
  can: TicketAction[];
}
/** GET /orgs/{org}/artisans/: verified artisans to choose from. */
export interface DirectoryArtisan {
  id: string;
  display_name: string;
  trades: Trade[];
  service_areas: string[];
  city: string;
  state: string;
  bio: string;
  years_experience: number | null;
  is_verified: boolean;
  verified_at: ISODateTime | null;
  rating_avg: number | null;
  rating_count: number;
  jobs_completed: number;
  jobs_with_us: number;
}
/** GET/POST /vouch/{token}/ (public): what a guarantor or reference sees. */
export interface PublicVoucher {
  kind: "guarantor" | "reference";
  full_name: string;
  artisan_name: string;
  trades: string[];
  status: "pending" | "confirmed" | "declined" | "expired";
}

// ---- Estates and security (Phase 5) -------------------------------------------------------------

/** GET /orgs/{org}/estates/ */
export interface Estate {
  id: string;
  name: string;
  address: string;
  city: string;
  state: string;
  join_code: string;
  is_active: boolean;
  panic_enabled: boolean;
  alert_residents: boolean;
  gate_instructions: string;
  property: string;
  houses: number;
  verified_residents: number;
  pending_residents: number;
  created_at: ISODateTime;
}
export interface House {
  id: string;
  label: string;
}
export type EstateMemberStatus = "pending" | "approved" | "suspended" | "removed";
export type EstateMemberRole = "resident" | "exco";
/** GET /orgs/{org}/estate-members/ */
export interface EstateMember {
  id: string;
  estate: string;
  full_name: string;
  phone_number: string;
  unit: string | null;
  house: string;
  house_label: string;
  role: EstateMemberRole;
  status: EstateMemberStatus;
  status_reason: string;
  approved_at: ISODateTime | null;
  has_app: boolean;
  created_at: ISODateTime;
}
/** GET /orgs/{org}/dues-plans/ (amount is a major-unit decimal string) */
export interface DuesPlan {
  id: string;
  estate: string;
  name: string;
  amount: string;
  currency: string;
  frequency: RentFrequency;
  start_date: ISODate;
  is_active: boolean;
  created_at: ISODateTime;
}
export interface Announcement {
  id: string;
  estate: string;
  title: string;
  body: string;
  audience: "all" | "exco";
  urgent: boolean;
  push_sent: number;
  sms_sent: number;
  created_at: ISODateTime;
}
export type GatePassStatus = "active" | "used" | "expired" | "cancelled";
export interface GateEvent {
  id: string;
  kind: "check_in" | "check_out" | "denied";
  note: string;
  by_name: string;
  created_at: ISODateTime;
}
/** What the gate sees for a pass (POST /orgs/{org}/gate/verify/, GET /orgs/{org}/gate/). No visitor phone. */
export interface GateCheck {
  id: string;
  estate: string;
  visitor_name: string;
  kind: "visitor" | "artisan" | "delivery";
  host_name: string;
  house: string;
  artisan: { display_name: string; is_verified: boolean; trade: string } | null;
  valid_from: ISODateTime;
  valid_to: ISODateTime;
  max_uses: number;
  uses: number;
  status: GatePassStatus;
  note: string;
  events: GateEvent[];
}
export type PanicKind = "help" | "robbery" | "kidnapping" | "fire" | "medical" | "suspicious_person" | "drill";
export type AlertStatus = "triggered" | "acknowledged" | "responding" | "resolved" | "false_alarm" | "cancelled";
/** GET /orgs/{org}/alerts/ (the security desk). */
export interface PanicAlert {
  id: string;
  estate: string;
  estate_name: string;
  kind: PanicKind;
  status: AlertStatus;
  silent: boolean;
  channel: string;
  raised_by_name: string;
  raised_by_phone: string;
  house: string;
  location: { lat: number; lng: number; accuracy?: number } | null;
  false_alarms_90d: number;
  created_at: ISODateTime;
  acknowledged_at: ISODateTime | null;
  responding_at: ISODateTime | null;
  closed_at: ISODateTime | null;
  close_note: string;
}
export interface AlertDelivery {
  id: string;
  audience: "staff" | "resident" | "raiser";
  channel: "push" | "sms" | "ws";
  status: "queued" | "sent" | "delivered" | "acknowledged" | "failed";
  name: string;
  phone_number: string;
  error: string;
  sent_at: ISODateTime | null;
  delivered_at: ISODateTime | null;
  fallback_for: string | null;
}
export interface IncidentNote {
  id: string;
  kind: string;
  note: string;
  author_name: string;
  created_at: ISODateTime;
}
export interface ChannelMetrics {
  sent: number;
  delivered: number;
  failed: number;
  first_delivery_seconds: number | null;
}
export interface PanicAlertDetail extends PanicAlert {
  notes: IncidentNote[];
  deliveries: AlertDelivery[];
  metrics: {
    recipients: number;
    by_channel: { push: ChannelMetrics; sms: ChannelMetrics };
    staff_reached: number;
    staff_total: number;
    acknowledge_seconds: number | null;
  };
}
/** The live desk's WebSocket payload (alert summary). */
export interface DeskAlert {
  id: string;
  estate: string;
  kind: PanicKind;
  kind_label: string;
  status: AlertStatus;
  silent: boolean;
  raised_by_name: string;
  raised_by_phone: string;
  house: string;
  location: { lat: number; lng: number; accuracy?: number } | null;
  created_at: ISODateTime;
}
export interface DeliveryReport {
  alerts: number;
  drills: number;
  false_alarms: number;
  median_first_delivery_seconds: number | null;
}
