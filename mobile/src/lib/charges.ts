import type { Charge, MyLease } from "@/api";

import { toKobo } from "./money";

/**
 * Charges from different landlords must be paid separately (POST /me/pay/ rejects mixing).
 * Grouped by the charge's organization (the landlord); the landlord's phone comes from a lease, when known.
 */
export type ChargeGroup = {
  key: string;
  landlord: string;
  landlordPhone: string | null;
  currency: string;
  charges: Charge[];
  totalKobo: number;
  overdueKobo: number;
  overdueCount: number;
};

export const byDueDate = (a: Charge, b: Charge) =>
  a.due_date < b.due_date ? -1 : a.due_date > b.due_date ? 1 : a.created_at.localeCompare(b.created_at);

export function isOutstanding(c: Charge): boolean {
  return c.status === "open" || c.status === "part_paid";
}

export function groupKeyFor(charge: Charge, leases: MyLease[]): { key: string; landlord: string; phone: string | null } {
  const lease = charge.lease ? leases.find((l) => l.id === charge.lease) : undefined;
  return {
    key: `org:${charge.organization}`,
    landlord: charge.organization_name,
    phone: lease?.landlord_phone || null,
  };
}

export function groupCharges(charges: Charge[], leases: MyLease[]): ChargeGroup[] {
  const groups = new Map<string, ChargeGroup>();
  for (const c of [...charges].filter(isOutstanding).sort(byDueDate)) {
    const { key: base, landlord, phone } = groupKeyFor(c, leases);
    const key = `${base}|${c.currency}`;
    let g = groups.get(key);
    if (!g) {
      g = { key, landlord, landlordPhone: phone, currency: c.currency, charges: [], totalKobo: 0, overdueKobo: 0, overdueCount: 0 };
      groups.set(key, g);
    }
    const bal = toKobo(c.balance);
    g.charges.push(c);
    g.totalKobo += bal;
    if (c.is_overdue) {
      g.overdueKobo += bal;
      g.overdueCount += 1;
    }
  }
  // Most urgent landlord first.
  return [...groups.values()].sort((a, b) => b.overdueKobo - a.overdueKobo || byDueDate(a.charges[0]!, b.charges[0]!));
}

export type RentSummary = {
  totals: { currency: string; totalKobo: number; overdueKobo: number }[];
  overdueCount: number;
  nextDue: Charge | null;
};

export function summarise(charges: Charge[]): RentSummary {
  const outstanding = charges.filter(isOutstanding).sort(byDueDate);
  const totals = new Map<string, { currency: string; totalKobo: number; overdueKobo: number }>();
  for (const c of outstanding) {
    const t = totals.get(c.currency) ?? { currency: c.currency, totalKobo: 0, overdueKobo: 0 };
    const bal = toKobo(c.balance);
    t.totalKobo += bal;
    if (c.is_overdue) t.overdueKobo += bal;
    totals.set(c.currency, t);
  }
  return {
    totals: [...totals.values()],
    overdueCount: outstanding.filter((c) => c.is_overdue).length,
    nextDue: outstanding.find((c) => !c.is_overdue) ?? outstanding[0] ?? null,
  };
}
