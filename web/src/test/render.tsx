import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";

import { ToastProvider } from "../components";
import { AuthProvider } from "../lib/auth";
import { makeOrgContext, OrgContext } from "../lib/org";
import type { Organization, Role } from "../lib/types";

export const ORG_ID = "11111111-1111-1111-1111-111111111111";

export function makeOrg(role: Role = "owner", overrides: Partial<Organization> = {}): Organization {
  return {
    id: ORG_ID,
    name: "Adeyemi Properties",
    kind: "landlord",
    country: "NG",
    currency: "NGN",
    timezone: "Africa/Lagos",
    phone_number: "",
    email: "",
    address: "",
    rent_reminders_enabled: true,
    my_role: role,
    created_at: "2026-10-01T09:00:00Z",
    ...overrides,
  };
}

export function testQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}

/** Shows the current location so tests can assert navigation. */
export function LocationProbe() {
  const loc = useLocation();
  return <div data-testid="location">{loc.pathname + loc.search}</div>;
}

/** Render an org screen at `url`, matched by `path` (relative to /orgs/:orgId/). */
export function renderOrgScreen(
  ui: ReactElement,
  { path, url, role = "owner" }: { path: string; url: string; role?: Role },
) {
  const org = makeOrg(role);
  const client = testQueryClient();
  return render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <ToastProvider>
          <MemoryRouter initialEntries={[`/orgs/${ORG_ID}/${url}`]}>
            <OrgContext.Provider value={makeOrgContext(org, [org])}>
              <Routes>
                <Route path={`/orgs/:orgId/${path}`} element={ui} />
                <Route path="*" element={<LocationProbe />} />
              </Routes>
            </OrgContext.Provider>
          </MemoryRouter>
        </ToastProvider>
      </AuthProvider>
    </QueryClientProvider>,
  );
}
