/** Test helpers (not shipped: nothing in the app imports this). */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react-native";
import type { ReactElement } from "react";

export type Call = { url: string; method: string; headers: Record<string, string>; body: unknown };
export type Route = (call: Call) => Response | Promise<Response> | undefined;

export function json(status: number, body?: unknown, headers: Record<string, string> = {}) {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

/** Replace global fetch with a router; returns the recorded calls. */
export function mockFetch(route: Route): Call[] {
  const calls: Call[] = [];
  globalThis.fetch = jest.fn(async (input: string, init: RequestInit = {}) => {
    const call: Call = {
      url: String(input),
      method: init.method ?? "GET",
      headers: (init.headers as Record<string, string>) ?? {},
      body: typeof init.body === "string" ? JSON.parse(init.body) : undefined,
    };
    calls.push(call);
    const res = await route(call);
    if (!res) throw new Error(`Unexpected fetch ${call.method} ${call.url}`);
    return res;
  }) as unknown as typeof fetch;
  return calls;
}

export function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { retry: false } } });
  return { client, ...render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>) };
}

export const user = {
  id: "u1",
  phone_number: "+2348012345678",
  email: null,
  first_name: "Ada",
  last_name: "Obi",
  country: "NG",
  preferred_language: "en",
  is_phone_verified: true,
  is_email_verified: false,
  has_login_pin: true,
  has_transaction_pin: false,
  created_at: "2026-10-01T00:00:00Z",
};

export const lease = {
  id: "lease-1",
  unit_label: "Flat 2",
  property_name: "Palm Court",
    organization: "org-1",
    organization_name: "Bello Properties",
  property_address: "12 Allen Avenue, Ikeja",
  landlord: "Bello Properties",
  landlord_phone: "+2348099999999",
  start_date: "2026-01-01",
  end_date: "2027-01-01",
  rent_amount: "1500000.00",
  rent_frequency: "annual",
  service_charge_amount: "100000.00",
  currency: "NGN",
  status: "active",
};

export function charge(overrides: Record<string, unknown> = {}) {
  return {
    id: "c1",
    lease: "lease-1",
    kind: "rent",
    description: "",
    period_start: "2026-10-01",
    period_end: "2027-09-30",
    due_date: "2026-10-01",
    amount: "1500000.00",
    amount_paid: "0.00",
    balance: "1500000.00",
    currency: "NGN",
    status: "open",
    is_overdue: false,
    waived_reason: "",
    tenant_name: "Ada Obi",
    unit_label: "Flat 2",
    property_name: "Palm Court",
    organization: "org-1",
    organization_name: "Bello Properties",
    created_at: "2026-09-01T00:00:00Z",
    ...overrides,
  };
}

export const page = <T,>(results: T[], next: string | null = null) => ({ next, previous: null, results });
