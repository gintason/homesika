import { fireEvent, screen, waitFor } from "@testing-library/react-native";

import Home from "@/app/(app)/(tabs)/index";
import { useSession } from "@/store/session";
import tokens from "@/theme/tokens";
import { charge, json, lease, mockFetch, page, renderWithClient } from "@/testing/utils";

beforeEach(() => {
  useSession.setState({ status: "ready", profile: { firstName: "Ada", lastName: "Obi", phone: "+2348012345678" } });
});

const routes =
  (leases: unknown, charges: unknown) =>
  (c: { url: string }) => {
    if (c.url.includes("/api/v1/me/leases/")) return json(200, leases);
    if (c.url.includes("/api/v1/me/charges/")) return json(200, charges);
    return undefined;
  };

describe("Home: my rent", () => {
  it("shows skeletons while loading", () => {
    globalThis.fetch = jest.fn(() => new Promise(() => {})) as unknown as typeof fetch; // never resolves
    renderWithClient(<Home />);
    expect(screen.getAllByTestId("skeleton").length).toBeGreaterThan(0);
    expect(screen.getByText("Hello, Ada")).toBeTruthy();
  });

  it("explains how to get linked when the landlord hasn't added this number", async () => {
    mockFetch(routes([], page([])));
    renderWithClient(<Home />);
    expect(await screen.findByText("Nothing to show yet")).toBeTruthy();
    expect(screen.getByText(/Ask your landlord to add your number \+234 801 234 5678/)).toBeTruthy();
  });

  it("shows 'all paid up' when there's a lease but nothing owed", async () => {
    mockFetch(routes([lease], page([])));
    renderWithClient(<Home />);
    expect(await screen.findByText("You're all paid up")).toBeTruthy();
    expect(screen.getByText("Palm Court · Flat 2")).toBeTruthy();
  });

  it("shows an error with a retry that recovers", async () => {
    let fail = true;
    mockFetch((c) => (fail ? json(500, { error: { code: "server_error", message: "Boom" } }) : routes([lease], page([]))(c)));
    renderWithClient(<Home />);
    const retry = await screen.findByRole("button", { name: "Try again" });
    expect(screen.getByText(/We couldn't load this/)).toBeTruthy();
    fail = false;
    fireEvent.press(retry);
    expect(await screen.findByText("You're all paid up")).toBeTruthy();
  });

  it("shows total owed, highlights overdue and the next due charge, with a Pay button", async () => {
    const calls = mockFetch(
      routes(
        [lease],
        page([
          charge({ id: "c2", kind: "service_charge", due_date: "2026-12-01", balance: "100000.00" }),
          charge({ id: "c1", due_date: "2026-09-01", balance: "750000.50", status: "part_paid", is_overdue: true }),
        ]),
      ),
    );
    renderWithClient(<Home />);
    // Exact kobo sum, shown in the summary card and the landlord card.
    expect(await screen.findAllByText("₦850,000.50")).toHaveLength(2);
    expect(screen.getByTestId("overdue-highlight")).toBeTruthy();
    expect(screen.getByText("Overdue (1): ₦750,000.50")).toBeTruthy();
    expect(screen.getByText(/Service charge · Due 1 Dec 2026/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Pay ₦850,000.50" })).toBeTruthy();
    expect(screen.getByText("Bello Properties")).toBeTruthy();
    expect(calls.find((c) => c.url.includes("/me/charges/"))!.url).toContain("page_size=100");
  });

  it("keeps showing loaded data when a refresh fails (offline)", async () => {
    let fail = false;
    mockFetch((c) => (fail ? Promise.reject(new TypeError("Network request failed")) : routes([lease], page([charge()]))(c)));
    const { client } = renderWithClient(<Home />);
    expect(await screen.findByRole("button", { name: "Pay ₦1,500,000.00" })).toBeTruthy();
    fail = true;
    await client.refetchQueries();
    await waitFor(() => expect(screen.getByText(/No internet connection/)).toBeTruthy());
    expect(screen.getByRole("button", { name: "Pay ₦1,500,000.00" })).toBeTruthy();
  });

  it("reads the shared design tokens", () => {
    expect(tokens.color.primary[800]).toBe("#0B2B63");
    expect(tokens.size.touchTarget).toBe(48);
  });
});
