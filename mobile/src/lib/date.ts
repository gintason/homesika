/** Dates from the API: "YYYY-MM-DD" (due dates) or ISO timestamps (paid_at). Shown in en-NG style. */

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-10-05" -> "5 Oct 2026" (no timezone shift: it's a calendar date). */
export function formatDate(value: string | null | undefined): string {
  if (!value) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (!m) return value;
  const [, y, mo, d] = m;
  return `${Number(d)} ${MONTHS[Number(mo) - 1] ?? ""} ${y}`;
}

/** ISO timestamp -> "5 Oct 2026, 14:30" in Lagos time (WAT, UTC+1, no DST). */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso;
  const lagos = new Date(t + 60 * 60 * 1000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${lagos.getUTCDate()} ${MONTHS[lagos.getUTCMonth()]} ${lagos.getUTCFullYear()}, ${pad(lagos.getUTCHours())}:${pad(lagos.getUTCMinutes())}`;
}

/** Today's date in Lagos as "YYYY-MM-DD" (string comparison works for ISO dates). */
export function todayLagos(now = Date.now()): string {
  return new Date(now + 60 * 60 * 1000).toISOString().slice(0, 10);
}
