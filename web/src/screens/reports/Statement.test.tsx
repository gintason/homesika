import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import * as download from "../../lib/download";
import { mockFetch } from "../../test/fetch";
import { ORG_ID, renderOrgScreen } from "../../test/render";
import { Statement } from "./Statement";

const BASE = `/api/v1/orgs/${ORG_ID}`;
const STATEMENT = {
  period: { start: "2026-09-01", end: "2026-09-30" },
  currency: "NGN",
  totals: { billed: "800000.00", collected: "650000.00", unallocated: "5000.00", expenses: "120000.00", net: "535000.00", outstanding_now: "150000.00" },
  by_property: [
    { property: "Palm Court", billed: "800000.00", collected: "650000.00", expenses: "100000.00", net: "550000.00" },
    { property: "General", billed: "0.00", collected: "0.00", expenses: "20000.00", net: "-20000.00" },
  ],
  expenses_by_category: { repairs: "100000.00", utilities: "20000.00" },
  collections: [
    { date: "2026-09-03", tenant: "Chidi Okafor", property: "Palm Court", unit: "Flat 2", for: "Rent", channel: "bank_transfer", receipt: "RCT-000001", amount: "650000.00" },
  ],
  expense_lines: [],
};

describe("Monthly statement", () => {
  it("renders totals and the by-property table, and downloads the CSV", async () => {
    const save = vi.spyOn(download, "saveBlob").mockImplementation(() => undefined);
    const m = mockFetch({
      [`GET ${BASE}/properties/`]: { body: [] },
      [`GET ${BASE}/statements/`]: (req) =>
        req.search.get("export") === "csv"
          ? { raw: "a,b\n", headers: { "Content-Type": "text/csv", "Content-Disposition": 'attachment; filename="statement-2026-09.csv"' } }
          : { body: STATEMENT },
    });
    renderOrgScreen(<Statement />, { path: "statement", url: "statement" });

    fireEvent.change(screen.getByLabelText("Month"), { target: { value: "2026-09" } });
    expect(await screen.findByText(/₦\s?650,000\.00/, { selector: "p" })).toBeInTheDocument();
    expect(screen.getByText("September 2026")).toBeInTheDocument();
    expect(screen.getByText("Overpayments not yet applied")).toBeInTheDocument();

    const table = screen.getByRole("table", { name: "By property" });
    expect(within(table).getByText("Palm Court")).toBeInTheDocument();
    expect(within(table).getByText(/-₦\s?20,000\.00|₦\s?-20,000\.00/)).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Expenses by category" })).toHaveTextContent("Repairs and maintenance");

    const statementCalls = m.find("GET", `${BASE}/statements/`);
    expect(statementCalls.at(-1)!.search.get("month")).toBe("2026-09");

    fireEvent.click(screen.getByRole("button", { name: "Download CSV" }));
    await waitFor(() => expect(save).toHaveBeenCalled());
    expect(save.mock.calls[0]![1]).toBe("statement-2026-09.csv");
    const csvCall = m.find("GET", `${BASE}/statements/`).find((c) => c.search.get("export") === "csv")!;
    expect(csvCall.search.get("month")).toBe("2026-09");
  });

  it("shows an empty state for a quiet month", async () => {
    const zero = "0.00";
    mockFetch({
      [`GET ${BASE}/properties/`]: { body: [] },
      [`GET ${BASE}/statements/`]: {
        body: {
          ...STATEMENT,
          totals: { billed: zero, collected: zero, unallocated: zero, expenses: zero, net: zero, outstanding_now: zero },
          by_property: [],
          expenses_by_category: {},
          collections: [],
        },
      },
    });
    renderOrgScreen(<Statement />, { path: "statement", url: "statement" });
    expect(await screen.findByRole("heading", { name: "No activity this month" })).toBeInTheDocument();
  });
});
