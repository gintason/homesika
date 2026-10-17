import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";

import { AppRoutes } from "./App";
import { ToastProvider } from "./components";
import { session } from "./lib/session";
import { mockFetch } from "./test/fetch";
import { makeOrg, ORG_ID } from "./test/render";

function renderApp(url: string) {
  return render(
    <ToastProvider>
      <MemoryRouter initialEntries={[url]}>
        <AppRoutes />
      </MemoryRouter>
    </ToastProvider>,
  );
}

const USER = { id: "u1", phone_number: "+2348031234567", email: null, first_name: "Ada", last_name: "Obi", country: "NG", preferred_language: "en", is_phone_verified: true, is_email_verified: false, has_login_pin: true, has_transaction_pin: true, created_at: "" };

describe("App routing", () => {
  it("sends signed-out visitors to sign in", async () => {
    mockFetch({});
    renderApp(`/orgs/${ORG_ID}/payments`);
    expect(await screen.findByRole("heading", { name: "Sign in to Homesika" })).toBeInTheDocument();
  });

  it("restores the session from the refresh token and opens the org dashboard", async () => {
    window.localStorage.setItem("hs.refresh", "stored-refresh");
    mockFetch({
      "POST /api/v1/auth/refresh/": { body: { access: "acc", refresh: "rotated" } },
      "GET /api/v1/me/": { body: USER },
      "GET /api/v1/orgs/": { body: [makeOrg("agent")] },
      [`GET /api/v1/orgs/${ORG_ID}/dashboard/`]: {
        body: { overdue_amount: "450000.00", overdue_charges: 3, due_next_30_days: "1200000.00", units: 10, occupied_units: 8, currency: "NGN" },
      },
      [`GET /api/v1/orgs/${ORG_ID}/conversations/`]: {
        body: { next: null, previous: null, results: [{ id: "c1" }, { id: "c2" }] },
      },
    });
    renderApp("/");
    expect(await screen.findByText(/₦\s?450,000\.00/)).toBeInTheDocument();
    expect(screen.getByText("3 overdue charges")).toBeInTheDocument();
    expect(screen.getByText("8 of 10")).toBeInTheDocument();

    // Agents can see properties and tenants but not payments or the statement.
    const nav = screen.getAllByRole("navigation", { name: "Main" })[0]!;
    expect(within(nav).getByRole("link", { name: "Tenants" })).toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "Payments" })).not.toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "Monthly statement" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Record a payment" })).not.toBeInTheDocument();
    expect(session.getRefresh()).toBe("rotated");

    // Phase 2: agents work listings and the inbox; the Inbox entry shows how many need a person.
    expect(within(nav).getByRole("link", { name: "Listings" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Leads" })).toBeInTheDocument();
    expect(await within(nav).findByRole("link", { name: /^Inbox\W*2 need a person$/ })).toHaveAttribute("href", `/orgs/${ORG_ID}/inbox`);
    expect(screen.getAllByRole("button", { name: "Ask Homesika" }).length).toBeGreaterThan(0);
  });

  it("opens the public listing page without signing in", async () => {
    mockFetch({
      "GET /api/v1/listings/LST-1/": {
        body: {
          ref: "LST-1", title: "Self-contain in Akoka", description: "", features: [], area: "Akoka", city: "Lagos", bedrooms: 1, bathrooms: 1,
          rent_amount: "400000.00", rent_period: "year", currency: "NGN", landlord: "Obi Properties", photos: [], published_at: null, slots: [],
        },
      },
    });
    renderApp("/l/LST-1");
    expect(await screen.findByRole("heading", { name: "Self-contain in Akoka" })).toBeInTheDocument();
  });

  it("first run: a user with no organization is asked to create one", async () => {
    window.localStorage.setItem("hs.refresh", "r");
    mockFetch({
      "POST /api/v1/auth/refresh/": { body: { access: "acc", refresh: "r2" } },
      "GET /api/v1/me/": { body: USER },
      "GET /api/v1/orgs/": { body: [] },
    });
    renderApp("/");
    expect(await screen.findByRole("heading", { name: "Set up your organization" })).toBeInTheDocument();
  });
});
