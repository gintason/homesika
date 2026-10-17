import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";

import { ToastProvider } from "../../components";
import type { DirectoryArtisan, Ticket } from "../../lib/types";
import { envelope, mockFetch } from "../../test/fetch";
import { ORG_ID, renderOrgScreen } from "../../test/render";
import { VouchPage } from "../vouch/VouchPage";
import { NewRepair } from "./NewRepair";
import { RepairDetail } from "./RepairDetail";
import { RepairsList } from "./RepairsList";

const BASE = `/api/v1/orgs/${ORG_ID}`;

const TICKET: Ticket = {
  id: "tk1",
  reference: "R0000A02",
  status: "awaiting_approval",
  category: "electrical",
  priority: "urgent",
  title: "Bathroom light not working",
  description: "Stopped two days ago; bulb changed.",
  access_notes: "After 4pm",
  channel: "whatsapp",
  raised_by_staff: false,
  unit: { id: "u1", label: "Flat 3C", property: "Palm Court", address: "12 Admiralty Way", city: "Lekki", organization: "Obi Properties" },
  tenant: { id: "tn1", full_name: "Grace Eze", phone_number: "+2348031110004" },
  closed_reason: "",
  approved_at: null,
  done_at: null,
  confirmed_at: null,
  auto_confirmed: false,
  created_at: "2026-10-14T09:00:00Z",
  updated_at: "2026-10-14T09:00:00Z",
  photos: [{ id: "ph1", stage: "report", url: "https://api.test/files/abc/", created_at: "2026-10-14T09:01:00Z" }],
  job: null,
  rating: null,
  events: [
    { id: "e1", kind: "created", actor_role: "tenant", actor_name: "Grace", note: "", internal: false, created_at: "2026-10-14T09:00:00Z" },
    { id: "e2", kind: "comment", actor_role: "staff", actor_name: "Bola", note: "Check the wiring", internal: true, created_at: "2026-10-14T10:00:00Z" },
  ],
  can: ["approve", "reject", "resolve", "cancel", "comment", "photo"],
};

const KUNLE: DirectoryArtisan = {
  id: "ar1",
  display_name: "Kunle Sparks",
  trades: ["electrical"],
  service_areas: ["Lekki", "Ajah"],
  city: "Lagos",
  state: "Lagos",
  bio: "",
  years_experience: 8,
  is_verified: true,
  verified_at: "2026-09-01T00:00:00Z",
  rating_avg: 4.8,
  rating_count: 5,
  jobs_completed: 12,
  jobs_with_us: 2,
};

describe("Repairs list", () => {
  it("shows open requests with priority and filters by status", async () => {
    const m = mockFetch({ [`GET ${BASE}/tickets/`]: { body: { next: null, previous: null, results: [TICKET] } } });
    renderOrgScreen(<RepairsList />, { path: "repairs", url: "repairs" });
    expect(await screen.findByRole("link", { name: "Bathroom light not working" })).toHaveAttribute(
      "href",
      `/orgs/${ORG_ID}/repairs/tk1`,
    );
    expect(screen.getByText("Urgent")).toBeInTheDocument();
    expect(screen.getByText("Grace Eze")).toBeInTheDocument();
    expect(screen.getByText("Not assigned")).toBeInTheDocument();
    expect(m.find("GET", `${BASE}/tickets/`)[0]!.search.get("status")).toBe("open");
    fireEvent.change(screen.getByLabelText("Show"), { target: { value: "awaiting_approval" } });
    await waitFor(() => expect(m.find("GET", `${BASE}/tickets/`).at(-1)!.search.get("status")).toBe("awaiting_approval"));
    expect(screen.getByRole("link", { name: "Log a repair" })).toBeInTheDocument();
  });

  it("hides 'Log a repair' from a viewer", async () => {
    mockFetch({ [`GET ${BASE}/tickets/`]: { body: { next: null, previous: null, results: [] } } });
    renderOrgScreen(<RepairsList />, { path: "repairs", url: "repairs", role: "viewer" });
    expect(await screen.findByText("No repair requests here")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Log a repair" })).toBeNull();
  });
});

describe("Repair detail", () => {
  it("approves with a note, then assigns a Verified artisan", async () => {
    let ticket = TICKET;
    const m = mockFetch({
      [`GET ${BASE}/tickets/tk1/`]: () => ({ body: ticket }),
      [`POST ${BASE}/tickets/tk1/approve/`]: () => {
        ticket = { ...TICKET, status: "approved", can: ["assign", "reject", "resolve", "cancel", "comment", "photo"] };
        return { body: ticket };
      },
      [`GET ${BASE}/artisans/`]: { body: [KUNLE] },
      [`POST ${BASE}/tickets/tk1/assign/`]: () => ({ body: { ...ticket, status: "assigned" } }),
    });
    renderOrgScreen(<RepairDetail />, { path: "repairs/:ticketId", url: "repairs/tk1" });
    expect(await screen.findByRole("heading", { name: "Bathroom light not working" })).toBeInTheDocument();
    expect(screen.getByAltText("Photo 1 of the problem")).toHaveAttribute("src", "https://api.test/files/abc/");
    expect(screen.getByText("Check the wiring")).toBeInTheDocument();
    expect(screen.getByText("(Team only)")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    const dialog = screen.getByRole("dialog", { name: "Approve this repair?" });
    fireEvent.change(within(dialog).getByLabelText(/Note to the tenant/), { target: { value: "Electrician coming" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(m.find("POST", `${BASE}/tickets/tk1/approve/`)).toHaveLength(1));
    expect(m.find("POST", `${BASE}/tickets/tk1/approve/`)[0]!.body).toEqual({ note: "Electrician coming" });

    fireEvent.click(await screen.findByRole("button", { name: "Assign an artisan" }));
    const drawer = screen.getByRole("dialog", { name: "Choose a Verified artisan" });
    expect(await within(drawer).findByText("Kunle Sparks")).toBeInTheDocument();
    expect(within(drawer).getByText(/Used 2 times by you/)).toBeInTheDocument();
    const search = m.find("GET", `${BASE}/artisans/`)[0]!.search;
    expect([search.get("trade"), search.get("area")]).toEqual(["electrical", "Lekki"]);
    fireEvent.click(within(drawer).getByRole("button", { name: "Assign Kunle Sparks" }));
    await waitFor(() => expect(m.find("POST", `${BASE}/tickets/tk1/assign/`)).toHaveLength(1));
    expect(m.find("POST", `${BASE}/tickets/tk1/assign/`)[0]!.body).toEqual({ artisan: "ar1", note: "" });
  });

  it("needs a reason to reject and shows server errors", async () => {
    const m = mockFetch({
      [`GET ${BASE}/tickets/tk1/`]: { body: TICKET },
      [`POST ${BASE}/tickets/tk1/reject/`]: envelope(409, "ticket_wrong_state", "This repair request has moved on."),
    });
    renderOrgScreen(<RepairDetail />, { path: "repairs/:ticketId", url: "repairs/tk1" });
    fireEvent.click(await screen.findByRole("button", { name: "Don't approve" }));
    const dialog = screen.getByRole("dialog", { name: "Don't approve this repair?" });
    const confirm = within(dialog).getByRole("button", { name: "Don't approve" });
    expect(confirm).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText(/Tell the tenant why/), { target: { value: "Tenant damage" } });
    fireEvent.click(confirm);
    expect(await within(dialog).findByText("This repair request has moved on.")).toBeInTheDocument();
    expect(m.find("POST", `${BASE}/tickets/tk1/reject/`)[0]!.body).toEqual({ reason: "Tenant damage" });
  });

  it("an agent can manage but not approve; posts an internal comment", async () => {
    const m = mockFetch({
      [`GET ${BASE}/tickets/tk1/`]: { body: TICKET },
      [`POST ${BASE}/tickets/tk1/comments/`]: { status: 201, body: TICKET.events[1] },
    });
    renderOrgScreen(<RepairDetail />, { path: "repairs/:ticketId", url: "repairs/tk1", role: "agent" });
    await screen.findByRole("heading", { name: "Bathroom light not working" });
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Don't approve" })).toBeNull();
    expect(screen.getByRole("button", { name: "Fixed another way" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Comment"), { target: { value: "Called Grace" } });
    fireEvent.click(screen.getByLabelText(/Team only/));
    fireEvent.click(screen.getByRole("button", { name: "Post comment" }));
    await waitFor(() => expect(m.find("POST", `${BASE}/tickets/tk1/comments/`)).toHaveLength(1));
    expect(m.find("POST", `${BASE}/tickets/tk1/comments/`)[0]!.body).toEqual({ note: "Called Grace", internal: true });
  });

  it("shows the artisan, visit and phone once accepted", async () => {
    mockFetch({
      [`GET ${BASE}/tickets/tk1/`]: {
        body: {
          ...TICKET,
          status: "assigned",
          can: ["reassign", "cancel", "comment", "photo"],
          job: {
            id: "j1",
            status: "accepted",
            artisan: { id: "ar1", display_name: "Kunle Sparks", is_verified: true, rating_avg: 4.8, rating_count: 5, jobs_completed: 12, phone_number: "+2348031110030" },
            offer_expires_at: "2026-10-15T09:00:00Z",
            scheduled_for: "2026-10-16T13:00:00Z",
            started_at: null,
            completed_at: null,
            completion_note: "",
          },
        },
      },
    });
    renderOrgScreen(<RepairDetail />, { path: "repairs/:ticketId", url: "repairs/tk1" });
    expect(await screen.findByText("Kunle Sparks")).toBeInTheDocument();
    expect(screen.getByText("Verified")).toBeInTheDocument();
    expect(screen.getByText(/4\.8 from 5 ratings/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Assign someone else" })).toBeInTheDocument();
    expect(screen.getByText(/0803 111 0030|\+234 803 111 0030/)).toBeInTheDocument();
  });
});

describe("Log a repair", () => {
  it("creates a staff repair with an Idempotency-Key and opens it", async () => {
    const m = mockFetch({
      [`GET ${BASE}/units/`]: { body: [{ id: "u9", property: "p1", property_name: "Vacant Block", label: "Flat 9", kind: "flat", bedrooms: 2, default_rent_amount: null, status: "vacant", meter_number: "", disco: "", created_at: "" }] },
      [`POST ${BASE}/tickets/`]: { status: 201, body: { ...TICKET, id: "tk9" } },
    });
    renderOrgScreen(<NewRepair />, { path: "repairs/new", url: "repairs/new" });
    await screen.findByRole("option", { name: "Flat 9, Vacant Block" });
    fireEvent.change(screen.getByLabelText("Unit"), { target: { value: "u9" } });
    fireEvent.change(screen.getByLabelText("Type of work"), { target: { value: "painting" } });
    fireEvent.change(screen.getByLabelText(/Short title/), { target: { value: "Repaint before letting" } });
    fireEvent.change(screen.getByLabelText(/Describe the problem/), { target: { value: "Whole flat needs a coat." } });
    fireEvent.click(screen.getByRole("button", { name: "Save repair" }));
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent(`/orgs/${ORG_ID}/repairs/tk9`));
    const post = m.find("POST", `${BASE}/tickets/`)[0]!;
    expect(post.body).toMatchObject({ unit: "u9", category: "painting", title: "Repaint before letting" });
    expect(post.headers["Idempotency-Key"]).toBeTruthy();
  });
});

describe("Guarantor page", () => {
  const renderVouch = () =>
    render(
      <ToastProvider>
        <MemoryRouter initialEntries={["/v/tok123"]}>
          <Routes>
            <Route path="/v/:token" element={<VouchPage />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>,
    );
  const V = { kind: "guarantor", full_name: "Uncle Sule", artisan_name: "Musa Plumbing Works", trades: ["Plumbing"], status: "pending" };

  it("asks plainly and records a yes", async () => {
    const m = mockFetch({
      "GET /api/v1/vouch/tok123/": { body: V },
      "POST /api/v1/vouch/tok123/": { body: { ...V, status: "confirmed" } },
    });
    renderVouch();
    expect(await screen.findByRole("heading", { name: "Be a guarantor for Musa Plumbing Works?" })).toBeInTheDocument();
    expect(screen.getByText("Hello Uncle Sule,")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/Anything to add/), { target: { value: "My nephew" } });
    fireEvent.click(screen.getByRole("button", { name: "Yes, I vouch for them" }));
    expect(await screen.findByText("Thank you. Your confirmation has been recorded.")).toBeInTheDocument();
    const post = m.find("POST", "/api/v1/vouch/tok123/")[0]!;
    expect(post.body).toEqual({ confirm: true, comment: "My nephew" });
    expect(post.headers.Authorization).toBeUndefined();
  });

  it("explains an invalid or used link", async () => {
    mockFetch({ "GET /api/v1/vouch/tok123/": envelope(404, "voucher_link_invalid", "This link isn't valid any more.") });
    renderVouch();
    expect(await screen.findAllByText("This link isn't valid any more. Ask the artisan to send a new one.")).not.toHaveLength(0);
  });
});
