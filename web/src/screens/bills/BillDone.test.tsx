import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";

import { ToastProvider } from "../../components";
import { envelope, mockFetch } from "../../test/fetch";
import { BillDone } from "./BillDone";

const REF = "BIL-XYZ789";
const PATH = `/api/v1/bills/${REF}/status/`;

function renderAt(ref = REF) {
  return render(
    <ToastProvider>
      <MemoryRouter initialEntries={[`/bills/${ref}/done`]}>
        <Routes>
          <Route path="/bills/:reference/done" element={<BillDone intervalMs={1} />} />
        </Routes>
      </MemoryRouter>
    </ToastProvider>,
  );
}

describe("Bill done page", () => {
  it("shows the receipt number when delivered, and stops polling", async () => {
    const m = mockFetch({ [`GET ${PATH}`]: { body: { status: "delivered", receipt_number: "BRC-000042" } } });
    renderAt();
    expect(await screen.findByText("Done!")).toBeInTheDocument();
    expect(screen.getByText("Your receipt number is BRC-000042.")).toBeInTheDocument();
    expect(screen.getByText(/sent the token or details to your phone by SMS or WhatsApp/)).toBeInTheDocument();
    expect(screen.getByText(/Homesika app/)).toBeInTheDocument();
    await new Promise((r) => setTimeout(r, 30));
    expect(m.find("GET", PATH)).toHaveLength(1);
    expect(m.find("GET", PATH)[0]!.headers.Authorization).toBeUndefined();
  });

  it("keeps polling while processing, then stops on delivered", async () => {
    const m = mockFetch({
      [`GET ${PATH}`]: (_req, nth) => ({
        body: nth < 3 ? { status: "processing", receipt_number: null } : { status: "delivered", receipt_number: "BRC-1" },
      }),
    });
    renderAt();
    expect(await screen.findByText("Your receipt number is BRC-1.")).toBeInTheDocument();
    await new Promise((r) => setTimeout(r, 30));
    expect(m.find("GET", PATH)).toHaveLength(3);
  });

  it("says it is being delivered when still processing after polling", async () => {
    const m = mockFetch({ [`GET ${PATH}`]: { body: { status: "processing", receipt_number: null } } });
    renderAt();
    expect(await screen.findByText("Being delivered")).toBeInTheDocument();
    expect(screen.getByText(/You'll get an SMS/)).toBeInTheDocument();
    expect(m.find("GET", PATH)).toHaveLength(5);
  });

  it.each([
    ["refund_pending", /will be refunded to your card or account within 1 to 5 working days/],
    ["refunded", /refunded your money to your card or account\. It can take 1 to 5 working days/],
  ])("explains the refund when %s", async (status, copy) => {
    const m = mockFetch({ [`GET ${PATH}`]: { body: { status, receipt_number: null } } });
    renderAt();
    expect(await screen.findByText("We couldn't deliver this")).toBeInTheDocument();
    expect(screen.getByText(copy)).toBeInTheDocument();
    expect(m.find("GET", PATH)).toHaveLength(1);
  });

  it("says payment isn't confirmed yet after polling, and can check again", async () => {
    const m = mockFetch({ [`GET ${PATH}`]: { body: { status: "awaiting_payment", receipt_number: null } } });
    renderAt();
    expect(await screen.findByText("Payment not confirmed yet")).toBeInTheDocument();
    expect(screen.getByText(/If money was taken from your account, it will be confirmed automatically/)).toBeInTheDocument();
    expect(m.find("GET", PATH)).toHaveLength(5);
    fireEvent.click(screen.getByRole("button", { name: "Check again" }));
    expect(await screen.findByText("Payment not confirmed yet")).toBeInTheDocument();
    expect(m.find("GET", PATH)).toHaveLength(10);
  });

  it("shows expired without more polling", async () => {
    const m = mockFetch({ [`GET ${PATH}`]: { body: { status: "expired", receipt_number: null } } });
    renderAt();
    expect(await screen.findByText("This payment has expired")).toBeInTheDocument();
    expect(m.find("GET", PATH)).toHaveLength(1);
  });

  it("handles an unknown reference (404) without retrying", async () => {
    const m = mockFetch({ "GET /api/v1/bills/NOPE/status/": envelope(404, "not_found", "Not found.") });
    renderAt("NOPE");
    expect(await screen.findByText(/couldn't find this payment/)).toBeInTheDocument();
    await new Promise((r) => setTimeout(r, 30));
    expect(m.find("GET", "/api/v1/bills/NOPE/status/")).toHaveLength(1);
  });

  it("keeps trying through network errors, then says it couldn't reach Homesika", async () => {
    const m = mockFetch({ [`GET ${PATH}`]: new TypeError("Failed to fetch") });
    renderAt();
    expect(await screen.findByText(/couldn't reach Homesika/)).toBeInTheDocument();
    expect(m.find("GET", PATH)).toHaveLength(5);
    expect(screen.getByRole("button", { name: "Check again" })).toBeInTheDocument();
  });
});
