/** Visit times to offer: today/tomorrow, 10am/2pm, only those still ahead. "later" = agree by phone. */
export function visitChoices(now = new Date()): { value: string; day: "today" | "tomorrow"; part: "morning" | "afternoon" }[] {
  const out: { value: string; day: "today" | "tomorrow"; part: "morning" | "afternoon" }[] = [];
  for (const [offset, day] of [
    [0, "today"],
    [1, "tomorrow"],
  ] as const) {
    for (const [hour, part] of [
      [10, "morning"],
      [14, "afternoon"],
    ] as const) {
      const d = new Date(now);
      d.setDate(d.getDate() + offset);
      d.setHours(hour, 0, 0, 0);
      if (d.getTime() > now.getTime() + 30 * 60 * 1000) out.push({ value: d.toISOString(), day, part });
    }
  }
  return out;
}

/** "01/05/1990" (or 1-5-1990, 01.05.1990) -> "1990-05-01"; null if it isn't a real date. */
export function parseDob(raw: string): string | null {
  const m = /^\s*(\d{1,2})[/.\- ](\d{1,2})[/.\- ](\d{4})\s*$/.exec(raw);
  if (!m) return null;
  const [d, mo, y] = [Number(m[1]), Number(m[2]), Number(m[3])];
  const date = new Date(Date.UTC(y, mo - 1, d));
  if (date.getUTCFullYear() !== y || date.getUTCMonth() !== mo - 1 || date.getUTCDate() !== d) return null;
  return `${y}-${String(mo).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}
