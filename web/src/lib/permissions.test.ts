import { can, capabilitiesOf } from "./permissions";
import type { Role } from "./types";

// Copied from backend/apps/orgs/permissions.py CAPABILITIES (Phase 2 capabilities only).
const NEW_CAPS = ["listing.view", "listing.manage", "inbox.view", "inbox.reply", "kb.manage"] as const;
const BACKEND: Record<Role, string[]> = {
  owner: [...NEW_CAPS],
  manager: ["listing.view", "listing.manage", "inbox.view", "inbox.reply", "kb.manage"],
  accountant: ["listing.view", "inbox.view"],
  agent: ["listing.view", "listing.manage", "inbox.view", "inbox.reply"],
  viewer: ["listing.view", "inbox.view"],
  estate_admin: [],
  security: [],
};

describe("capabilities copy", () => {
  it.each(Object.entries(BACKEND))("%s has exactly the backend's Phase 2 capabilities", (role, expected) => {
    const granted = NEW_CAPS.filter((c) => can(role as Role, c));
    expect(granted).toEqual(NEW_CAPS.filter((c) => expected.includes(c)));
  });

  it("matches the backend's full sets for the roles that changed", () => {
    expect([...capabilitiesOf("agent")].sort()).toEqual(
      ["org.view", "property.view", "tenant.view", "listing.view", "listing.manage", "inbox.view", "inbox.reply"].sort(),
    );
    expect([...capabilitiesOf("viewer")].sort()).toEqual(
      ["org.view", "property.view", "tenant.view", "payment.view", "expense.view", "report.view", "listing.view", "inbox.view"].sort(),
    );
    expect([...capabilitiesOf("owner")]).toEqual(["*"]);
  });
});
