import type { Ionicons } from "@expo/vector-icons";

import type { BillCategory, Biller, BillOrderStatus, MyLease } from "@/api";
import type { BadgeStatus } from "@/components/Badge";

import { fromKobo, toKobo } from "./money";

export const BILL_CATEGORIES: readonly BillCategory[] = ["airtime", "data", "cable_tv", "electricity"];

export const CATEGORY_ICONS: Record<BillCategory, keyof typeof Ionicons.glyphMap> = {
  airtime: "phone-portrait-outline",
  data: "wifi-outline",
  cable_tv: "tv-outline",
  electricity: "flash-outline",
};

export function isBillCategory(value: unknown): value is BillCategory {
  return typeof value === "string" && (BILL_CATEGORIES as readonly string[]).includes(value);
}

/** Quick amount chips (naira), shown only when inside the biller's min/max. */
export const QUICK_AMOUNTS: Partial<Record<BillCategory, number[]>> = {
  airtime: [100, 200, 500, 1000],
  electricity: [1000, 2000, 5000, 10000],
};

/** Statuses the backend won't move on from by itself soon (stop polling). */
export const FINAL_STATUSES: readonly BillOrderStatus[] = ["delivered", "refunded", "expired"];

/** Bill status -> an existing badge colour (the label always says the status in words). */
export const STATUS_BADGE: Record<BillOrderStatus, BadgeStatus> = {
  awaiting_payment: "open",
  processing: "part_paid",
  delivered: "paid",
  refund_pending: "part_paid",
  refunded: "waived",
  expired: "void",
};

export type AmountError = "required" | "invalid" | "whole" | "min" | "max";

/**
 * What the person typed -> a whole-naira decimal string for the API ("1,500" -> "1500.00").
 * The backend only accepts whole naira and the biller's min/max.
 */
export function parseNairaAmount(
  raw: string,
  biller?: Pick<Biller, "min_amount" | "max_amount"> | null,
): { amount: string } | { error: AmountError } {
  const cleaned = raw.replace(/[\s,₦]/g, "");
  if (!cleaned) return { error: "required" };
  const m = /^(\d+)(?:\.(\d{0,2}))?$/.exec(cleaned);
  if (!m) return { error: "invalid" };
  if (m[2] && /[1-9]/.test(m[2])) return { error: "whole" };
  let kobo: number;
  try {
    kobo = toKobo(m[1]);
  } catch {
    return { error: "invalid" };
  }
  if (kobo <= 0) return { error: "invalid" };
  if (biller?.min_amount && kobo < safeKobo(biller.min_amount)) return { error: "min" };
  if (biller?.max_amount && kobo > safeKobo(biller.max_amount)) return { error: "max" };
  return { amount: fromKobo(kobo) };
}

function safeKobo(amount: string): number {
  try {
    return toKobo(amount);
  } catch {
    return 0;
  }
}

/** Quick chips that fit the biller's limits. */
export function quickAmounts(category: BillCategory, biller?: Pick<Biller, "min_amount" | "max_amount"> | null): number[] {
  const all = QUICK_AMOUNTS[category] ?? [];
  return all.filter((naira) => {
    const kobo = naira * 100;
    if (biller?.min_amount && kobo < safeKobo(biller.min_amount)) return false;
    if (biller?.max_amount && kobo > safeKobo(biller.max_amount)) return false;
    return true;
  });
}

const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");

/**
 * A unit's `disco` (a name like "Ikeja Electric", a code like "ikeja-electric", or an abbreviation like
 * "IKEDC") -> the electricity biller, matched case-insensitively. null if nothing matches.
 */
export function matchDisco(billers: Biller[], disco: string | null | undefined): Biller | null {
  const wanted = norm(disco ?? "");
  if (!wanted) return null;
  for (const b of billers) {
    const abbrev = /\(([^)]+)\)/.exec(b.name)?.[1] ?? "";
    const plainName = b.name.replace(/\([^)]*\)/g, "");
    const names = [b.code, b.name, plainName, abbrev].map(norm).filter(Boolean);
    if (names.includes(wanted)) return b;
  }
  return null;
}

/** My first active lease whose unit has a meter number (for prefilling electricity). */
export function leaseWithMeter(leases: MyLease[] | undefined): MyLease | null {
  return (leases ?? []).find((l) => l.status === "active" && Boolean(l.meter_number?.trim())) ?? null;
}

export const digitsOnly = (s: string) => s.replace(/\D/g, "");

/** Electricity tokens are read out / typed in groups of four: "1234 5678 9012 3456 7890". */
export function formatToken(token: string): string {
  const d = digitsOnly(token);
  return d.length === token.replace(/[\s-]/g, "").length && d.length > 4 ? d.replace(/(\d{4})(?=\d)/g, "$1 ") : token;
}

/** A detail from verify (`details` is provider-specific JSON): the string value, or "". */
export function detailText(details: Record<string, unknown> | undefined, key: string): string {
  const v = details?.[key];
  return typeof v === "string" || typeof v === "number" ? String(v).trim() : "";
}
