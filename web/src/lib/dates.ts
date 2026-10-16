/** Dates. Date-only API values ("2026-10-16") are treated as calendar dates, never shifted by time zone. */

const DATE_ONLY = /^(\d{4})-(\d{2})-(\d{2})$/;
const dateFmt = new Intl.DateTimeFormat("en-NG", { day: "numeric", month: "short", year: "numeric" });
const dateTimeFmt = new Intl.DateTimeFormat("en-NG", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "numeric",
  minute: "2-digit",
});
const monthFmt = new Intl.DateTimeFormat("en-NG", { month: "long", year: "numeric" });

function parseDateOnly(value: string): Date | null {
  const m = DATE_ONLY.exec(value);
  if (!m) return null;
  return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
}

/** "2026-10-16" or an ISO date-time -> "16 Oct 2026". */
export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const d = parseDateOnly(value) ?? new Date(value);
  return Number.isNaN(d.getTime()) ? value : dateFmt.format(d);
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : dateTimeFmt.format(d);
}

/** "2026-10" -> "October 2026" */
export function formatMonth(value: string): string {
  const d = parseDateOnly(`${value}-01`);
  return d ? monthFmt.format(d) : value;
}

const pad = (n: number) => String(n).padStart(2, "0");

/** Local calendar date as YYYY-MM-DD. */
export function toISODate(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function todayISO(): string {
  return toISODate(new Date());
}

export function currentMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`;
}

/** Add whole years to a YYYY-MM-DD date, minus one day (a one-year lease from 1 Jan ends 31 Dec). */
export function addYearsMinusDay(iso: string, years: number): string {
  const d = parseDateOnly(iso);
  if (!d) return "";
  d.setFullYear(d.getFullYear() + years);
  d.setDate(d.getDate() - 1);
  return toISODate(d);
}

/** Value for <input type="datetime-local"> for "now" in local time. */
export function nowLocalInput(): string {
  const d = new Date();
  return `${toISODate(d)}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** "2026-10-16T09:30" (local) -> ISO string with time zone, for the API. */
export function localInputToISO(value: string): string | null {
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}
