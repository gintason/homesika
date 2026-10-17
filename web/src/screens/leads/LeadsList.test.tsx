import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { mockFetch } from "../../test/fetch";
import { LEAD } from "../../test/fixtures";
import { ORG_ID, renderOrgScreen } from "../../test/render";
import { LeadsList } from "./LeadsList";

const BASE = `/api/v1/orgs/${ORG_ID}`;

describe("Leads", () => {
  it("filters by stage and changes a lead's stage with PATCH", async () => {
    const m = mockFetch({
      [`GET ${BASE}/leads/`]: { body: { next: null, previous: null, results: [LEAD] } },
      [`PATCH ${BASE}/leads/ld1/`]: { body: { ...LEAD, stage: "contacted" } },
    });
    renderOrgScreen(<LeadsList />, { path: "leads", url: "leads?stage=new" });
    fireEvent.click(await screen.findByRole("button", { name: "Bisi Ade" }));
    expect(m.find("GET", `${BASE}/leads/`)[0]!.search.get("stage")).toBe("new");

    const drawer = screen.getByRole("dialog", { name: "Bisi Ade" });
    expect(within(drawer).getByText("Is it still available?")).toBeInTheDocument();
    fireEvent.change(within(drawer).getByLabelText("Stage"), { target: { value: "contacted" } });
    await waitFor(() => expect(m.find("PATCH", `${BASE}/leads/ld1/`)).toHaveLength(1));
    expect(m.find("PATCH", `${BASE}/leads/ld1/`)[0]!.body).toEqual({ stage: "contacted" });

    fireEvent.change(within(drawer).getByLabelText(/Your notes/), { target: { value: "Called, will visit Sat" } });
    fireEvent.click(within(drawer).getByRole("button", { name: "Save notes" }));
    await waitFor(() => expect(m.find("PATCH", `${BASE}/leads/ld1/`)).toHaveLength(2));
    expect(m.find("PATCH", `${BASE}/leads/ld1/`)[1]!.body).toEqual({ notes: "Called, will visit Sat" });
  });
});
