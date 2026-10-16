import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";

import { ToastProvider } from "../../components";
import { browser } from "../../lib/browser";
import { envelope, mockFetch } from "../../test/fetch";
import { MockCheckout } from "./MockCheckout";
import { PayDone } from "./PayDone";
import { PayPage } from "./PayPage";

const LINK = {
  reference: "HSK-ABC123",
  landlord: "Adeyemi Properties",
  tenant_first_name: "Chidi",
  description: "",
  amount: "525000.50",
  currency: "NGN",
  status: "pending",
  expires_at: "2026-10-30T00:00:00Z",
  items: [{ description: "Rent", due_date: "2026-09-01", unit: "Flat 2" }],
  receipt_number: null,
  mock: true,
};

function renderAt(url: string) {
  return render(
    <ToastProvider>
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          <Route path="/pay/:reference" element={<PayPage />} />
          <Route path="/pay/:reference/done" element={<PayDone intervalMs={1} />} />
          <Route path="/pay/:reference/mock-checkout" element={<MockCheckout />} />
        </Routes>
      </MemoryRouter>
    </ToastProvider>,
  );
}

describe("Public pay page", () => {
  it("shows the landlord, items and amount, and redirects to checkout", async () => {
    const assign = vi.spyOn(browser, "assign").mockImplementation(() => undefined);
    const m = mockFetch({
      "GET /api/v1/pay/HSK-ABC123/": { body: LINK },
      "POST /api/v1/pay/HSK-ABC123/checkout/": { body: { checkout_url: "https://checkout.example/xyz", gateway: "paystack" } },
    });
    renderAt("/pay/HSK-ABC123");
    expect(await screen.findByText("Hi Chidi,")).toBeInTheDocument();
    expect(screen.getByText("Adeyemi Properties has asked you to pay:")).toBeInTheDocument();
    expect(screen.getByText(/Rent · Unit Flat 2/)).toBeInTheDocument();
    const pay = screen.getByRole("button", { name: /Pay ₦\s?525,000\.50 now/ });
    fireEvent.click(pay);
    await waitFor(() => expect(assign).toHaveBeenCalledWith("https://checkout.example/xyz"));
    expect(m.find("POST", "/api/v1/pay/HSK-ABC123/checkout/")[0]!.headers.Authorization).toBeUndefined();
  });

  it("explains when the landlord has no payout account yet", async () => {
    mockFetch({
      "GET /api/v1/pay/HSK-ABC123/": { body: LINK },
      "POST /api/v1/pay/HSK-ABC123/checkout/": envelope(
        409,
        "no_payout_account",
        "Online payment isn't set up yet: the landlord needs to add a payout bank account.",
      ),
    });
    renderAt("/pay/HSK-ABC123");
    fireEvent.click(await screen.findByRole("button", { name: /Pay/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("payout bank account");
  });

  it("shows a friendly message for an unknown link", async () => {
    mockFetch({ "GET /api/v1/pay/NOPE/": envelope(404, "not_found", "Not found.") });
    renderAt("/pay/NOPE");
    expect(await screen.findByText(/couldn't find this payment link/)).toBeInTheDocument();
  });

  it("does not offer to pay an expired link", async () => {
    mockFetch({ "GET /api/v1/pay/HSK-ABC123/": { body: { ...LINK, status: "expired" } } });
    renderAt("/pay/HSK-ABC123");
    expect(await screen.findByText(/has expired/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Pay/ })).not.toBeInTheDocument();
  });
});

describe("Mock checkout", () => {
  it("is clearly labelled as a test and completes the mock payment", async () => {
    const m = mockFetch({
      "GET /api/v1/pay/HSK-ABC123/": { body: LINK },
      "POST /api/v1/pay/HSK-ABC123/mock-complete/": { body: { status: "paid" } },
      "GET /api/v1/pay/HSK-ABC123/status/": { body: { status: "paid", receipt_number: "RCT-000001" } },
    });
    renderAt("/pay/HSK-ABC123/mock-checkout");
    expect(await screen.findByRole("heading", { level: 1, name: "TEST PAYMENT – no real money" })).toBeInTheDocument();
    expect(screen.getByText(/No card is charged/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Simulate successful payment" }));
    expect(await screen.findByText("Payment received")).toBeInTheDocument();
    expect(m.find("POST", "/api/v1/pay/HSK-ABC123/mock-complete/")[0]!.body).toEqual({ success: true });
    expect(screen.getByText("Receipt RCT-000001")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download receipt (PDF)" })).toHaveAttribute("href", "/api/v1/pay/HSK-ABC123/receipt/");
  });

  it("can simulate a failure", async () => {
    const m = mockFetch({
      "GET /api/v1/pay/HSK-ABC123/": { body: LINK },
      "POST /api/v1/pay/HSK-ABC123/mock-complete/": { body: { status: "failed" } },
    });
    renderAt("/pay/HSK-ABC123/mock-checkout");
    fireEvent.click(await screen.findByRole("button", { name: "Simulate failed payment" }));
    expect(await screen.findByText("Payment not completed")).toBeInTheDocument();
    expect(m.find("POST", "/api/v1/pay/HSK-ABC123/mock-complete/")[0]!.body).toEqual({ success: false });
  });

  it("refuses to run when the link isn't on the mock gateway", async () => {
    mockFetch({ "GET /api/v1/pay/HSK-ABC123/": { body: { ...LINK, mock: false } } });
    renderAt("/pay/HSK-ABC123/mock-checkout");
    expect(await screen.findByText("Test payments aren't available here.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Simulate/ })).not.toBeInTheDocument();
  });
});

describe("Pay done page", () => {
  it("polls a few times, then says it is still processing", async () => {
    const m = mockFetch({ "GET /api/v1/pay/HSK-ABC123/status/": { body: { status: "pending", receipt_number: null } } });
    renderAt("/pay/HSK-ABC123/done");
    expect(await screen.findByText("Still processing")).toBeInTheDocument();
    expect(m.find("GET", "/api/v1/pay/HSK-ABC123/status/")).toHaveLength(5);
    expect(screen.getByRole("button", { name: "Check again" })).toBeInTheDocument();
  });
});
