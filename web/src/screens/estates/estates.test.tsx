import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import type { DuesPlan, Estate, EstateMember } from "../../lib/types";
import { mockFetch } from "../../test/fetch";
import { ORG_ID, renderOrgScreen } from "../../test/render";
import { EstateDetail } from "./EstateDetail";
import { EstatesList, splitHouses } from "./EstatesList";

const BASE = `/api/v1/orgs/${ORG_ID}`;
const page = <T,>(results: T[]) => ({ body: { next: null, previous: null, results } });

const ESTATE: Estate = {
  id: "es1",
  name: "Palm Grove Estate",
  address: "1 Palm Ave, Lekki",
  city: "Lagos",
  state: "Lagos",
  join_code: "K7PM2Q",
  is_active: true,
  panic_enabled: true,
  alert_residents: true,
  gate_instructions: "",
  property: "p1",
  houses: 3,
  verified_residents: 1,
  pending_residents: 1,
  created_at: "2026-10-01T09:00:00Z",
};

const PENDING: EstateMember = {
  id: "m1",
  estate: "es1",
  full_name: "Ngozi Eze",
  phone_number: "+2348031112222",
  unit: null,
  house: "a1",
  house_label: "a1",
  role: "resident",
  status: "pending",
  status_reason: "",
  approved_at: null,
  has_app: true,
  created_at: "2026-10-14T09:00:00Z",
};

const HOUSES = [
  { id: "u1", label: "A1" },
  { id: "u2", label: "A2" },
];

describe("Estates", () => {
  it("splits house labels", () => {
    expect(splitHouses("A1, A2\nB1,,A2 ")).toEqual(["A1", "A2", "B1"]);
  });

  it("creates an estate with its houses", async () => {
    const m = mockFetch({
      [`GET ${BASE}/estates/`]: page([]),
      [`POST ${BASE}/estates/`]: { status: 201, body: ESTATE },
    });
    renderOrgScreen(<EstatesList />, { path: "estates", url: "estates" });
    expect(await screen.findByText("No estates yet")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Add estate" }));
    const dialog = screen.getByRole("dialog", { name: "Add estate" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create" }));
    expect(await within(dialog).findAllByText("This field is required.")).toHaveLength(2);
    fireEvent.change(within(dialog).getByLabelText("Estate name"), { target: { value: "Palm Grove Estate" } });
    fireEvent.change(within(dialog).getByLabelText("Address"), { target: { value: "1 Palm Ave" } });
    fireEvent.change(within(dialog).getByLabelText(/Houses or flats/), { target: { value: "A1, A2\nB1" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create" }));
    await waitFor(() => expect(m.find("POST", `${BASE}/estates/`)).toHaveLength(1));
    expect(m.find("POST", `${BASE}/estates/`)[0]!.body).toMatchObject({ name: "Palm Grove Estate", houses: ["A1", "A2", "B1"] });
    expect(await screen.findByTestId("location")).toHaveTextContent(`/orgs/${ORG_ID}/estates/es1`);
  });

  it("approves a waiting resident after choosing the house", async () => {
    const m = mockFetch({
      [`GET ${BASE}/estates/es1/`]: { body: ESTATE },
      [`GET ${BASE}/estate-members/`]: page([PENDING]),
      [`GET ${BASE}/estates/es1/houses/`]: { body: HOUSES },
      [`POST ${BASE}/estate-members/m1/approve/`]: { body: { ...PENDING, status: "approved" } },
    });
    renderOrgScreen(<EstateDetail />, { path: "estates/:estateId", url: "estates/es1" });
    expect(await screen.findByText("K7PM2Q")).toBeInTheDocument();
    expect(await screen.findByText("Ngozi Eze")).toBeInTheDocument();
    expect(m.find("GET", `${BASE}/estate-members/`)[0]!.search.get("status")).toBe("pending");
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    const dialog = screen.getByRole("dialog", { name: "Approve Ngozi Eze?" });
    expect(within(dialog).getByText("They typed: a1")).toBeInTheDocument();
    const confirm = within(dialog).getByRole("button", { name: "Approve" });
    expect(confirm).toBeDisabled();
    await within(dialog).findByRole("option", { name: "A1" });
    fireEvent.change(within(dialog).getByLabelText(/House/), { target: { value: "u1" } });
    fireEvent.click(confirm);
    await waitFor(() => expect(m.find("POST", `${BASE}/estate-members/m1/approve/`)).toHaveLength(1));
    expect(m.find("POST", `${BASE}/estate-members/m1/approve/`)[0]!.body).toEqual({ unit: "u1" });
  });

  it("adds dues in naira and sends an announcement with an idempotency key", async () => {
    const plan: DuesPlan = {
      id: "dp1",
      estate: "es1",
      name: "Security levy",
      amount: "15000.00",
      currency: "NGN",
      frequency: "monthly",
      start_date: "2026-10-01",
      is_active: true,
      created_at: "2026-10-01T09:00:00Z",
    };
    const m = mockFetch({
      [`GET ${BASE}/estates/es1/`]: { body: ESTATE },
      [`GET ${BASE}/estate-members/`]: page([]),
      [`GET ${BASE}/estates/es1/houses/`]: { body: HOUSES },
      [`GET ${BASE}/dues-plans/`]: page([plan]),
      [`POST ${BASE}/dues-plans/`]: { status: 201, body: plan },
      [`GET ${BASE}/announcements/`]: page([]),
      [`POST ${BASE}/announcements/`]: {
        status: 201,
        body: { id: "a1", estate: "es1", title: "Water off", body: "Sat", audience: "all", urgent: false, push_sent: 3, sms_sent: 1, created_at: "2026-10-15T09:00:00Z" },
      },
    });
    renderOrgScreen(<EstateDetail />, { path: "estates/:estateId", url: "estates/es1" });
    fireEvent.click(await screen.findByRole("tab", { name: "Dues" }));
    expect(await screen.findByText("₦15,000.00")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/^Name/), { target: { value: "Service charge" } });
    fireEvent.change(screen.getByLabelText("Amount"), { target: { value: "5,000" } });
    fireEvent.click(screen.getByRole("button", { name: "Add dues" }));
    await waitFor(() => expect(m.find("POST", `${BASE}/dues-plans/`)).toHaveLength(1));
    expect(m.find("POST", `${BASE}/dues-plans/`)[0]!.body).toMatchObject({ name: "Service charge", amount: "5000.00", estate: "es1" });

    fireEvent.click(screen.getByRole("tab", { name: "Announcements" }));
    fireEvent.change(await screen.findByLabelText("Title"), { target: { value: "Water off" } });
    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "Sat" } });
    fireEvent.click(screen.getByRole("button", { name: "Send announcement" }));
    expect(await screen.findByText("Announcement sent: 3 by app, 1 by SMS.")).toBeInTheDocument();
    expect(m.find("POST", `${BASE}/announcements/`)[0]!.headers["Idempotency-Key"]).toBeTruthy();
  });

  it("a viewer sees no management actions", async () => {
    mockFetch({
      [`GET ${BASE}/estates/es1/`]: { body: ESTATE },
      [`GET ${BASE}/estate-members/`]: page([PENDING]),
      [`GET ${BASE}/estates/es1/houses/`]: { body: HOUSES },
    });
    renderOrgScreen(<EstateDetail />, { path: "estates/:estateId", url: "estates/es1", role: "viewer" });
    expect(await screen.findByText("Ngozi Eze")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Make a new code" })).toBeNull();
    expect(screen.queryByRole("tab", { name: "Settings" })).toBeNull();
  });
});
