import type { Role } from "./types";

/**
 * Mirror of backend/apps/orgs/permissions.py CAPABILITIES. Used only to hide actions a role can't do;
 * the server enforces every check anyway. Keep in sync when the backend matrix changes.
 */
export type Capability =
  | "org.view"
  | "org.manage"
  | "property.view"
  | "property.manage"
  | "tenant.view"
  | "tenant.manage"
  | "lease.manage"
  | "charge.manage"
  | "payment.view"
  | "payment.record"
  | "payment.link"
  | "expense.view"
  | "expense.manage"
  | "report.view"
  | "members.view"
  | "members.manage"
  | "listing.view"
  | "listing.manage"
  | "inbox.view"
  | "inbox.reply"
  | "kb.manage";

const ALL = "*";

const CAPABILITIES: Record<Role, ReadonlySet<string>> = {
  owner: new Set([ALL]),
  manager: new Set([
    "org.view",
    "property.view",
    "property.manage",
    "tenant.view",
    "tenant.manage",
    "lease.manage",
    "charge.manage",
    "payment.view",
    "payment.record",
    "payment.link",
    "expense.view",
    "expense.manage",
    "report.view",
    "members.view",
    "listing.view",
    "listing.manage",
    "inbox.view",
    "inbox.reply",
    "kb.manage",
  ]),
  accountant: new Set([
    "org.view",
    "property.view",
    "tenant.view",
    "payment.view",
    "payment.record",
    "payment.link",
    "expense.view",
    "expense.manage",
    "report.view",
    "members.view",
    "listing.view",
    "inbox.view",
  ]),
  agent: new Set(["org.view", "property.view", "tenant.view", "listing.view", "listing.manage", "inbox.view", "inbox.reply"]),
  viewer: new Set([
    "org.view",
    "property.view",
    "tenant.view",
    "payment.view",
    "expense.view",
    "report.view",
    "listing.view",
    "inbox.view",
  ]),
  estate_admin: new Set(["org.view", "property.view", "members.view"]),
  security: new Set(["org.view"]),
};

/** The capabilities granted to a role ("*" for owner), for tests that compare with the backend. */
export function capabilitiesOf(role: Role): ReadonlySet<string> {
  return CAPABILITIES[role];
}

export function can(role: Role | null | undefined, capability: Capability): boolean {
  if (!role) return false;
  const caps = CAPABILITIES[role];
  if (!caps) return false;
  return caps.has(ALL) || caps.has(capability);
}
