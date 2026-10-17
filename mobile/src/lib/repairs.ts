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
