import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { envelope, mockFetch } from "../../test/fetch";
import { ORG_ID, renderOrgScreen } from "../../test/render";
import { RecordPayment } from "./RecordPayment";

const BASE = `/api/v1/orgs/${ORG_ID}`;
const TENANT = { id: "t1", full_name: "Chidi Okafor", phone_number: "+2348031234567", email: "", occupation: "", next_of_kin: "", id_document: "", notes: "", has_app: false, active_lease: null, created_at: "" };
const charge = (id: string, balance: string, kind = "rent") => ({
  id,
  lease: "l1",
  kind,
  description: "",
  period_start: null,
  period_end: null,
  due_date: "2026-09-01",
  amount: balance,
  amount_paid: "0.00",
  balance,
  currency: "NGN",
  status: "open",
  is_overdue: true,
  waived_reason: "",
  tenant_name: "Chidi Okafor",
  unit_label: "Flat 2",
  property_name: "Palm Court",
  created_at: "",
});

function routes(manual: Parameters<typeof mockFetch>[0][string]) {
  return mockFetch({
    [`GET ${BASE}/tenants/`]: { body: [TENANT] },
    [`GET ${BASE}/charges/`]: { body: { next: null, previous: null, results: [charge("c1", "500000.00"), charge("c2", "25000.50", "service_charge")] } },
    [`POST ${BASE}/payments/manual/`]: manual,
  });
}

describe("Record manual payment", () => {
  it("validates before sending anything", async () => {
    const m = routes({ status: 201, body: { id: "pay1" } });
    renderOrgScreen(<RecordPayment />, { path: "payments/new", url: "payments/new" });
    fireEvent.click(await screen.findByRole("button", { name: "Record payment" }));
    expect(await screen.findAllByText("This field is required.")).not.toHaveLength(0);
    expect(screen.getByLabelText("Amount")).toHaveAccessibleDescription("Enter an amount like 150000 or 150000.50.");
    expect(m.find("POST", `${BASE}/payments/manual/`)).toHaveLength(0);
  });

  it("sends the exact payload with an Idempotency-Key, and reuses the key when retrying", async () => {
    const m = routes((_req, nth) => (nth === 1 ? new TypeError("Failed to fetch") : { status: 201, body: { id: "pay1" } }));
    renderOrgScreen(<RecordPayment />, { path: "payments/new", url: "payments/new?tenant=t1" });

    const picker = await screen.findByRole("group", { name: "Apply to these charges" });
    fireEvent.click(within(picker).getByRole("checkbox", { name: /Rent/ }));
    fireEvent.click(within(picker).getByRole("checkbox", { name: /Service charge/ }));
    // The amount is pre-filled with the exact sum of the ticked balances.
    expect(screen.getByLabelText("Amount")).toHaveValue("525,000.50");

    fireEvent.change(screen.getByLabelText("How it was paid"), { target: { value: "cash" } });
    fireEvent.change(screen.getByLabelText("Date paid"), { target: { value: "2026-10-01T10:30" } });
    fireEvent.change(screen.getByLabelText(/Note/), { target: { value: "Paid at the office" } });
    fireEvent.click(screen.getByRole("button", { name: "Record payment" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("couldn't reach Homesika");
    fireEvent.click(screen.getByRole("button", { name: "Record payment" }));
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent(`/orgs/${ORG_ID}/payments/pay1`));

    const posts = m.find("POST", `${BASE}/payments/manual/`);
    expect(posts).toHaveLength(2);
    expect(posts[1]!.body).toEqual({
      tenant: "t1",
      amount: "525000.50",
      channel: "cash",
      paid_at: new Date("2026-10-01T10:30").toISOString(),
      note: "Paid at the office",
      charges: ["c1", "c2"],
    });
    const key = posts[0]!.headers["Idempotency-Key"];
    expect(key).toMatch(/^[A-Za-z0-9_\-:.]{16,64}$/);
    expect(posts[1]!.headers["Idempotency-Key"]).toBe(key);
  });

  it("shows server field errors next to the field", async () => {
    routes(envelope(400, "validation_error", "Please check your input.", { paid_at: ["The payment date can't be in the future."] }));
    renderOrgScreen(<RecordPayment />, { path: "payments/new", url: "payments/new?tenant=t1" });
    await screen.findByRole("group", { name: "Apply to these charges" });
    fireEvent.change(screen.getByLabelText("Amount"), { target: { value: "1000" } });
    fireEvent.click(screen.getByRole("button", { name: "Record payment" }));
    expect(await screen.findByText("The payment date can't be in the future.")).toBeInTheDocument();
  });
});
