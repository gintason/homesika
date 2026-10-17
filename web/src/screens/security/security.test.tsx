import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";

import { session } from "../../lib/session";
import type { Estate, PanicAlert, PanicAlertDetail } from "../../lib/types";
import { mockFetch } from "../../test/fetch";
import { ORG_ID, renderOrgScreen } from "../../test/render";
import { AlertDetail } from "./AlertDetail";
import { SecurityDesk } from "./SecurityDesk";
import { deskSocketUrl } from "./useDeskSocket";

const BASE = `/api/v1/orgs/${ORG_ID}`;
const page = <T,>(results: T[]) => ({ body: { next: null, previous: null, results } });

class FakeSocket {
  static all: FakeSocket[] = [];
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;
  constructor(public url: string) {
    FakeSocket.all.push(this);
    setTimeout(() => this.onopen?.(), 0);
  }
  send(s: string) {
    this.sent.push(s);
  }
  close() {
    this.onclose?.({ code: 1000 });
  }
  emit(data: object) {
    act(() => this.onmessage?.({ data: JSON.stringify(data) }));
  }
}

const ESTATE = { id: "es1", name: "Palm Grove Estate" } as Estate;
const ALERT: PanicAlert = {
  id: "al1",
  estate: "es1",
  estate_name: "Palm Grove Estate",
  kind: "robbery",
  status: "triggered",
  silent: true,
  channel: "app",
  raised_by_name: "Ngozi Eze",
  raised_by_phone: "+2348031112222",
  house: "A1",
  location: { lat: 6.43, lng: 3.42, accuracy: 12 },
  false_alarms_90d: 1,
  created_at: "2026-10-15T09:00:00Z",
  acknowledged_at: null,
  responding_at: null,
  closed_at: null,
  close_note: "",
};

beforeEach(() => {
  FakeSocket.all = [];
  vi.stubGlobal("WebSocket", FakeSocket);
  session.setTokens({ access: "access-token" });
});

describe("Security desk", () => {
  it("builds the socket URL from the API host", () => {
    expect(deskSocketUrl("es1", "https://app.homesika.ng")).toBe("wss://app.homesika.ng/ws/estates/es1/desk/");
  });

  it("shows open alerts, goes live, and refreshes on a new alert", async () => {
    let open: PanicAlert[] = [];
    const m = mockFetch({
      [`GET ${BASE}/estates/`]: page([ESTATE]),
      [`GET ${BASE}/alerts/`]: (req) => (req.search.get("status") === "open" ? page(open) : page([])),
      [`GET ${BASE}/alerts/report/`]: { body: { alerts: 2, drills: 1, false_alarms: 1, median_first_delivery_seconds: 4.2 } },
      [`POST ${BASE}/alerts/al1/acknowledge/`]: { body: { ...ALERT, status: "acknowledged" } },
    });
    renderOrgScreen(<SecurityDesk />, { path: "security", url: "security" });
    expect(await screen.findByText("No open alerts")).toBeInTheDocument();
    expect(screen.getByText(/2 alerts · 1 tests · 1 false alarms/)).toBeInTheDocument();
    await waitFor(() => expect(FakeSocket.all).toHaveLength(1));
    const ws = FakeSocket.all[0]!;
    await waitFor(() => expect(ws.sent[0]).toBe(JSON.stringify({ type: "auth", token: "access-token" })));
    expect(ws.url).toMatch(/\/ws\/estates\/es1\/desk\/$/);
    ws.emit({ type: "ready" });
    expect(await screen.findByText("Live")).toBeInTheDocument();

    open = [ALERT];
    ws.emit({ type: "alert.new", alert: { ...ALERT, kind_label: "Robbery / break-in" } });
    expect(await screen.findByRole("link", { name: "Robbery / break-in" })).toHaveAttribute("href", `/orgs/${ORG_ID}/security/al1`);
    expect(screen.getByRole("alert")).toHaveTextContent("New alert: Robbery / break-in at A1");
    expect(screen.getByText("House A1")).toBeInTheDocument();
    expect(screen.getByText(/don't call or text the resident/)).toBeInTheDocument();
    expect(screen.getByText("1 false alarms in 90 days")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open map" })).toHaveAttribute("href", "https://www.google.com/maps?q=6.43,3.42");

    fireEvent.click(screen.getByRole("button", { name: "Seen" }));
    await waitFor(() => expect(m.find("POST", `${BASE}/alerts/al1/acknowledge/`)).toHaveLength(1));
  });

  it("needs a note to mark a false alarm; a guard can't send a test alert", async () => {
    const m = mockFetch({
      [`GET ${BASE}/estates/`]: page([ESTATE]),
      [`GET ${BASE}/alerts/`]: (req) => (req.search.get("status") === "open" ? page([ALERT]) : page([])),
      [`GET ${BASE}/alerts/report/`]: { body: { alerts: 0, drills: 0, false_alarms: 0, median_first_delivery_seconds: null } },
      [`POST ${BASE}/alerts/al1/false-alarm/`]: { body: { ...ALERT, status: "false_alarm" } },
    });
    renderOrgScreen(<SecurityDesk />, { path: "security", url: "security", role: "security" });
    fireEvent.click(await screen.findByRole("button", { name: "False alarm" }));
    expect(screen.queryByRole("button", { name: "Send a test alert" })).toBeNull();
    const dialog = screen.getByRole("dialog", { name: "False alarm" });
    const confirm = within(dialog).getByRole("button", { name: "False alarm" });
    expect(confirm).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText(/^Note/), { target: { value: "Child pressed it" } });
    fireEvent.click(confirm);
    await waitFor(() => expect(m.find("POST", `${BASE}/alerts/al1/false-alarm/`)).toHaveLength(1));
    expect(m.find("POST", `${BASE}/alerts/al1/false-alarm/`)[0]!.body).toEqual({ note: "Child pressed it" });
  });

  it("an owner sends a test alert", async () => {
    const m = mockFetch({
      [`GET ${BASE}/estates/`]: page([ESTATE]),
      [`GET ${BASE}/alerts/`]: page([]),
      [`GET ${BASE}/alerts/report/`]: { body: { alerts: 0, drills: 0, false_alarms: 0, median_first_delivery_seconds: null } },
      [`POST ${BASE}/alerts/drill/`]: { status: 201, body: { ...ALERT, kind: "drill" } },
    });
    renderOrgScreen(<SecurityDesk />, { path: "security", url: "security" });
    fireEvent.click(await screen.findByRole("button", { name: "Send a test alert" }));
    const dialog = screen.getByRole("dialog", { name: "Send a test alert?" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Send a test alert" }));
    await waitFor(() => expect(m.find("POST", `${BASE}/alerts/drill/`)).toHaveLength(1));
    expect(m.find("POST", `${BASE}/alerts/drill/`)[0]!.search.get("estate")).toBe("es1");
  });
});

describe("Alert detail", () => {
  it("shows delivery timings, the log and adds a note", async () => {
    const detail: PanicAlertDetail = {
      ...ALERT,
      status: "responding",
      notes: [{ id: "n1", kind: "triggered", note: "", author_name: "Ngozi Eze", created_at: "2026-10-15T09:00:00Z" }],
      deliveries: [
        { id: "d1", audience: "staff", channel: "push", status: "delivered", name: "Musa", phone_number: "+2348030000009", error: "", sent_at: "2026-10-15T09:00:01Z", delivered_at: "2026-10-15T09:00:03Z", fallback_for: null },
        { id: "d2", audience: "resident", channel: "sms", status: "failed", name: "", phone_number: "+2348031110003", error: "sms failed", sent_at: null, delivered_at: null, fallback_for: null },
      ],
      metrics: {
        recipients: 2,
        by_channel: {
          push: { sent: 1, delivered: 1, failed: 0, first_delivery_seconds: 3 },
          sms: { sent: 0, delivered: 0, failed: 1, first_delivery_seconds: null },
        },
        staff_reached: 1,
        staff_total: 1,
        acknowledge_seconds: 20,
      },
    };
    const m = mockFetch({
      [`GET ${BASE}/alerts/al1/`]: { body: detail },
      [`POST ${BASE}/alerts/al1/notes/`]: { status: 201, body: { id: "n2", kind: "note", note: "Gate closed", author_name: "Musa", created_at: "2026-10-15T09:05:00Z" } },
    });
    renderOrgScreen(<AlertDetail />, { path: "security/:alertId", url: "security/al1" });
    expect(await screen.findByText("Security and managers reached: 1 of 1")).toBeInTheDocument();
    expect(screen.getByText(/App: First delivered after 3 s/)).toBeInTheDocument();
    expect(screen.getByText(/SMS: Not confirmed yet/)).toBeInTheDocument();
    expect(screen.getByText("Failed (sms failed)")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "On our way" })).toBeNull();
    fireEvent.change(screen.getByLabelText("Add note"), { target: { value: "Gate closed" } });
    fireEvent.click(screen.getByRole("button", { name: "Add note" }));
    await waitFor(() => expect(m.find("POST", `${BASE}/alerts/al1/notes/`)).toHaveLength(1));
  });
});
