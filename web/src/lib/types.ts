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
