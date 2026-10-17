import { fireEvent, screen, waitFor } from "@testing-library/react";

import type { Analytics as AnalyticsData } from "../../lib/types";
import { mockFetch } from "../../test/fetch";
import { ORG_ID, renderOrgScreen } from "../../test/render";
import { Analytics } from "./Analytics";

const BASE = `/api/v1/orgs/${ORG_ID}`;
const DATA: AnalyticsData = {
  currency: "NGN",
  months: [
    { month: "2026-09-01", billed: "540000.00", collected: "300000.00", payments: 3, paid_against_billed: "300000.00", collection_rate: 55.6, charges: 4, paid_on_time: 2, on_time_rate: 50, dues_billed: "0.00", dues_collected: "0.00" },
    { month: "2026-10-01", billed: "810000.00", collected: "175000.00", payments: 2, paid_against_billed: "175000.00", collection_rate: 21.6, charges: 6, paid_on_time: 1, on_time_rate: 16.7, dues_billed: "15000.00", dues_collected: "15000.00" },
  ],
  now: {
    units: 8, occupied: 7, occupancy_rate: 87.5, arrears: "665000.00", tenants_in_arrears: 3, repairs_open: 2, repairs_reported_30d: 2,
    repair_median_days_90d: null, leads_30d: 2, leads_won_30d: 0, viewings_30d: 1, alerts_30d: 0, false_alarms_30d: 0,
  },
};

describe("Analytics", () => {
  it("shows the snapshot, the chart with tooltips, and the month-by-month table", async () => {
    const m = mockFetch({ [`GET ${BASE}/analytics/`]: { body: DATA } });
    renderOrgScreen(<Analytics />, { path: "analytics", url: "analytics" });
    expect(await screen.findByText("87.5%")).toBeInTheDocument();
    expect(screen.getByText("7 of 8")).toBeInTheDocument();
    expect(screen.getByText("₦665,000.00")).toBeInTheDocument();
    expect(screen.getByText("3 tenants owe")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Month by month" })).toBeInTheDocument();
    expect(screen.getByText("21.6%")).toBeInTheDocument();
    expect(screen.getByText("16.7% (1/6)")).toBeInTheDocument();
    const bar = screen.getByRole("graphics-symbol", { name: /October 2026: Collected ₦175,000.00/ });
    fireEvent.focus(bar);
    expect(screen.getByRole("tooltip")).toHaveTextContent("Collected ₦175,000.00");
    expect(m.find("GET", `${BASE}/analytics/`)[0]!.search.get("months")).toBe("6");
    fireEvent.change(screen.getByLabelText("Show"), { target: { value: "12" } });
    await waitFor(() => expect(m.find("GET", `${BASE}/analytics/`).at(-1)!.search.get("months")).toBe("12"));
  });
});
