import { fireEvent, screen, waitFor } from "@testing-library/react";

import type { Estate, GateCheck } from "../../lib/types";
import { envelope, mockFetch } from "../../test/fetch";
import { ORG_ID, renderOrgScreen } from "../../test/render";
import { GateDesk } from "./GateDesk";

const BASE = `/api/v1/orgs/${ORG_ID}`;
const page = <T,>(results: T[]) => ({ body: { next: null, previous: null, results } });
const PASS: GateCheck = {
  id: "gp1",
  estate: "es1",
  visitor_name: "Kunle",
  kind: "artisan",
  host_name: "Ngozi Eze",
  house: "A1",
  artisan: { display_name: "Kunle Plumbing Works", is_verified: true, trade: "plumbing" },
  valid_from: "2026-10-15T09:00:00Z",
  valid_to: "2026-10-15T21:00:00Z",
  max_uses: 1,
  uses: 0,
  status: "active",
  note: "",
  events: [],
};

describe("Gate", () => {
  it("checks a code, shows the Verified artisan and lets them in", async () => {
    const m = mockFetch({
      [`GET ${BASE}/estates/`]: page([{ id: "es1", name: "Palm Grove Estate" } as Estate]),
      [`GET ${BASE}/gate/`]: page([]),
      [`POST ${BASE}/gate/verify/`]: (req) =>
        (req.body as { code: string }).code === "123 456" ? { body: PASS } : envelope(404, "gate_pass_invalid", "No valid pass with that code."),
      [`POST ${BASE}/gate/gp1/check-in/`]: { body: { ...PASS, uses: 1, status: "used" } },
    });
    renderOrgScreen(<GateDesk />, { path: "gate", url: "gate", role: "security" });
    const input = await screen.findByLabelText("Visitor's code");
    const button = screen.getByRole("button", { name: "Check code" });
    fireEvent.change(input, { target: { value: "12a3" } });
    expect(input).toHaveValue("123");
    expect(button).toBeDisabled();
    fireEvent.change(input, { target: { value: "999999" } });
    fireEvent.click(button);
    expect(await screen.findByText("No valid pass with that code.")).toBeInTheDocument();
    fireEvent.change(input, { target: { value: "123 456" } });
    fireEvent.click(button);
    expect(await screen.findByText("Verified artisan")).toBeInTheDocument();
    expect(screen.getByText("Ngozi Eze, A1")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Let in" }));
    await waitFor(() => expect(m.find("POST", `${BASE}/gate/gp1/check-in/`)).toHaveLength(1));
    expect(await screen.findByText("Entries: 1 of 1")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Let in" })).toBeNull();
  });
});
