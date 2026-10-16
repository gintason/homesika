/**
 * Nigerian numbers to E.164, matching the backend's normalise_phone and adding the case of a
 * number typed after a fixed "+234" prefix (8012345678):
 *   08012345678 / 8012345678 / 2348012345678 / +234 801 234 5678 -> +2348012345678
 */
export function normalisePhone(raw: string): string {
  const digits = raw.replace(/[^\d+]/g, "");
  if (digits.startsWith("+")) return digits;
  if (digits.startsWith("234") && digits.length >= 13) return `+${digits}`;
  if (digits.startsWith("0") && digits.length === 11) return `+234${digits.slice(1)}`;
  if (/^[789]\d{9}$/.test(digits)) return `+234${digits}`;
  return digits;
}

/** Same rule as the backend's phone_validator. */
export function isValidPhone(e164: string): boolean {
  return /^\+[1-9]\d{7,14}$/.test(e164);
}

/** +2348012345678 -> "+234 801 234 5678" for display. */
export function formatPhone(e164: string | null | undefined): string {
  if (!e164) return "";
  const m = /^\+234(\d{3})(\d{3})(\d{4})$/.exec(e164);
  return m ? `+234 ${m[1]} ${m[2]} ${m[3]}` : e164;
}

/** Same rule as the backend's is_weak_pin: all one digit, or a straight run up or down. */
export function isWeakPin(pin: string): boolean {
  const digits = [...pin].map(Number);
  const steps = new Set(digits.slice(1).map((d, i) => d - (digits[i] ?? 0)));
  return new Set(digits).size === 1 || (steps.size === 1 && (steps.has(1) || steps.has(-1)));
}
