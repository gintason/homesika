/**
 * Nigerian phone numbers. People type 0803 123 4567, 803..., 234803... or +234 803...; the API wants
 * E.164 (+2348031234567). Mirrors backend normalise_phone() for the Nigerian default.
 */
export function normalisePhone(raw: string): string {
  const s = raw.replace(/[^\d+]/g, "");
  if (s.startsWith("+")) return s;
  if (s.startsWith("234")) return `+${s}`;
  if (s.startsWith("0") && s.length === 11) return `+234${s.slice(1)}`;
  if (/^[789]\d{9}$/.test(s)) return `+234${s}`;
  return s;
}

/** True for a Nigerian mobile number (+234 then 10 digits starting 7, 8 or 9). */
export function isValidNigerianPhone(raw: string): boolean {
  return /^\+234[789]\d{9}$/.test(normalisePhone(raw));
}

/** "+2348031234567" -> "0803 123 4567" for display. Other numbers are returned as they are. */
export function formatPhone(e164: string | null | undefined): string {
  if (!e164) return "—";
  const m = /^\+234(\d{3})(\d{3})(\d{4})$/.exec(e164);
  return m ? `0${m[1]} ${m[2]} ${m[3]}` : e164;
}
