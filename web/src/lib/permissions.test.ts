import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { can, capabilitiesOf } from "./permissions";
import type { Role } from "./types";

/** Reads CAPABILITIES straight from backend/apps/orgs/permissions.py, so the copy can't drift. */
function backendMatrix(): Record<string, string[]> {
  const src = readFileSync(resolve(__dirname, "../../../backend/apps/orgs/permissions.py"), "utf8");
  const body = src.slice(src.indexOf("CAPABILITIES"), src.indexOf("def can("));
  const out: Record<string, string[]> = {};
  for (const m of body.matchAll(/Role\.([A-Z_]+):\s*\{([^}]*)\}/g)) {
    const role = m[1]!.toLowerCase();
    out[role] = m[2]!.includes("ALL") ? ["*"] : [...m[2]!.matchAll(/"([a-z_.]+)"/g)].map((x) => x[1]!);
  }
  return out;
}

describe("capabilities copy", () => {
  const backend = backendMatrix();

  it("parses every backend role", () => {
    expect(Object.keys(backend).sort()).toEqual(
      ["accountant", "agent", "estate_admin", "manager", "owner", "security", "viewer"].sort(),
    );
  });

  it.each(Object.entries(backend))("%s has exactly the backend's capabilities", (role, expected) => {
    expect([...capabilitiesOf(role as Role)].sort()).toEqual([...expected].sort());
  });

  it("approving repairs is for owners and managers only", () => {
    expect(can("owner", "maintenance.approve")).toBe(true);
    expect(can("manager", "maintenance.approve")).toBe(true);
    expect(can("agent", "maintenance.approve")).toBe(false);
    expect(can("agent", "maintenance.manage")).toBe(true);
    expect(can("viewer", "maintenance.manage")).toBe(false);
  });
});
