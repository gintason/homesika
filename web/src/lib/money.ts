/**
 * Money. The API sends and accepts decimal strings in major units ("1500000.00"). We never do float
 * arithmetic on amounts: sums go through BigInt minor units (kobo) and back to a string.
 */

const DECIMALS = 2; // NGN and every currency we show today have 2 minor digits.
const formatters = new Map<string, Intl.NumberFormat>();

function formatter(currency: string): Intl.NumberFormat {
  let f = formatters.get(currency);
  if (!f) {
    f = new Intl.NumberFormat("en-NG", {
      style: "currency",
      currency,
      minimumFractionDigits: DECIMALS,
      maximumFractionDigits: DECIMALS,
    });
    formatters.set(currency, f);
  }
  return f;
}

const DECIMAL_RE = /^-?\d+(\.\d+)?$/;

/** "1500000.5" -> 150000050n. Throws on anything that isn't a plain decimal string. */
export function toMinor(amount: string): bigint {
  const s = amount.trim();
  if (!DECIMAL_RE.test(s)) throw new Error(`Not a decimal amount: ${amount}`);
  const negative = s.startsWith("-");
  const [whole = "0", frac = ""] = s.replace("-", "").split(".");
  if (frac.length > DECIMALS && /[1-9]/.test(frac.slice(DECIMALS))) {
    throw new Error(`Too many decimal places: ${amount}`);
  }
  const minor = BigInt(whole) * 10n ** BigInt(DECIMALS) + BigInt((frac + "00").slice(0, DECIMALS) || "0");
  return negative ? -minor : minor;
}

/** 150000050n -> "1500000.50" */
export function fromMinor(minor: bigint): string {
  const negative = minor < 0n;
  const abs = negative ? -minor : minor;
  const base = 10n ** BigInt(DECIMALS);
  const whole = abs / base;
  const frac = (abs % base).toString().padStart(DECIMALS, "0");
  return `${negative ? "-" : ""}${whole}.${frac}`;
}

/** Exact sum of decimal strings. */
export function sumMoney(amounts: Array<string | null | undefined>): string {
  return fromMinor(amounts.reduce<bigint>((acc, a) => (a ? acc + toMinor(a) : acc), 0n));
}

export function compareMoney(a: string, b: string): -1 | 0 | 1 {
  const d = toMinor(a) - toMinor(b);
  return d < 0n ? -1 : d > 0n ? 1 : 0;
}

export function isPositive(amount: string | null | undefined): boolean {
  if (!amount) return false;
  try {
    return toMinor(amount) > 0n;
  } catch {
    return false;
  }
}

/** "1500000.00" -> "₦1,500,000.00". Null/empty shows a dash. */
export function formatMoney(amount: string | null | undefined, currency = "NGN"): string {
  if (amount === null || amount === undefined || amount === "") return "—";
  const s = amount.trim();
  if (!DECIMAL_RE.test(s)) return s;
  // Intl formats decimal strings exactly (no float conversion) in current browsers.
  return formatter(currency).format(s as `${number}`);
}

/**
 * Parse what a person typed ("1,500,000", "₦ 2500.5", "1 000") into the API's decimal string
 * ("1500000.00"). Returns null when it isn't a valid amount (letters, 3+ decimals, several dots).
 */
export function parseMoneyInput(input: string): string | null {
  const cleaned = input.replace(/[₦,\s]/g, "").replace(/^NGN/i, "");
  if (!/^\d+(\.\d{0,2})?$/.test(cleaned)) return null;
  return fromMinor(toMinor(cleaned.endsWith(".") ? `${cleaned}0` : cleaned));
}

/** "1500000.5" -> "1,500,000.50" (no currency sign), for showing a typed amount back in its field. */
export function formatPlainAmount(amount: string): string {
  const parsed = parseMoneyInput(amount);
  if (parsed === null) return amount;
  const [whole = "0", frac = "00"] = parsed.split(".");
  return `${whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",")}.${frac}`;
}
