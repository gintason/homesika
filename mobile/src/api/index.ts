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
