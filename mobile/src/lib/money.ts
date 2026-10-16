/**
 * Money arrives from the API as decimal strings in major units ("1500000.00").
 * All arithmetic is done in integer minor units (kobo) — never with floats.
 * Safe up to Number.MAX_SAFE_INTEGER kobo (≈ ₦90 trillion).
 */

const SYMBOLS: Record<string, string> = { NGN: "₦", USD: "$", GBP: "£", EUR: "€", GHS: "GH₵" };

export function currencySymbol(currency: string): string {
  return SYMBOLS[currency] ?? `${currency} `;
}

/** "1500.5" -> 150050. Throws on anything that isn't a plain decimal with ≤ 2 places. */
export function toKobo(amount: string | null | undefined): number {
  const raw = (amount ?? "0").trim().replace(/,/g, "");
  const match = /^(-)?(\d+)(?:\.(\d{0,2}))?$/.exec(raw);
  if (!match) throw new Error(`Invalid money amount: ${amount}`);
  const [, sign, whole = "0", frac = ""] = match;
  const kobo = Number(whole) * 100 + Number(frac.padEnd(2, "0"));
  if (!Number.isSafeInteger(kobo)) throw new Error(`Amount too large: ${amount}`);
  return sign ? -kobo : kobo;
}

/** 150050 -> "1500.50" (what the API accepts). */
export function fromKobo(kobo: number): string {
  if (!Number.isInteger(kobo)) throw new Error("Kobo must be an integer");
  const sign = kobo < 0 ? "-" : "";
  const abs = Math.abs(kobo);
  return `${sign}${Math.floor(abs / 100)}.${String(abs % 100).padStart(2, "0")}`;
}

/** Sum decimal strings exactly. */
export function sumKobo(amounts: (string | null | undefined)[]): number {
  return amounts.reduce<number>((total, a) => total + toKobo(a), 0);
}

function group(whole: string): string {
  return whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

/** 150050 -> "₦1,500.50" (en-NG grouping, built from integers so no float rounding). */
export function formatKobo(kobo: number, currency = "NGN"): string {
  const sign = kobo < 0 ? "-" : "";
  const abs = Math.abs(kobo);
  return `${sign}${currencySymbol(currency)}${group(String(Math.floor(abs / 100)))}.${String(abs % 100).padStart(2, "0")}`;
}

/** "1500.5" -> "₦1,500.50". Invalid input shows ₦0.00 rather than crashing a list. */
export function formatMoney(amount: string | null | undefined, currency = "NGN"): string {
  try {
    return formatKobo(toKobo(amount), currency);
  } catch {
    return formatKobo(0, currency);
  }
}

/**
 * What the user typed -> decimal string for the API ("1,500.5" -> "1500.50"),
 * or null if it isn't a positive amount with at most 2 decimals.
 */
export function parseAmountInput(raw: string): string | null {
  const cleaned = raw.replace(/[\s,₦]/g, "");
  if (!/^\d+(\.\d{0,2})?$/.test(cleaned)) return null;
  try {
    const kobo = toKobo(cleaned);
    return kobo > 0 ? fromKobo(kobo) : null;
  } catch {
    return null;
  }
}
