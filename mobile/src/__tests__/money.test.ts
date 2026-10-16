import { groupCharges, summarise } from "@/lib/charges";
import { formatDate, formatDateTime } from "@/lib/date";
import { newIdempotencyKey } from "@/lib/idempotency";
import { formatKobo, formatMoney, fromKobo, parseAmountInput, sumKobo, toKobo } from "@/lib/money";
import { isValidPhone, isWeakPin, normalisePhone } from "@/lib/phone";
import { charge, lease } from "@/testing/utils";
import type { Charge, MyLease } from "@/api";

describe("money (integer kobo)", () => {
  it("parses decimal strings exactly", () => {
    expect(toKobo("1500000.00")).toBe(150000000);
    expect(toKobo("0.1")).toBe(10);
    expect(toKobo("12")).toBe(1200);
    expect(toKobo("1,250.05")).toBe(125005);
    expect(toKobo("-3.50")).toBe(-350);
    expect(() => toKobo("1.234")).toThrow();
    expect(() => toKobo("abc")).toThrow();
  });

  it("sums without float error (0.1 + 0.2 = 0.30)", () => {
    expect(sumKobo(["0.10", "0.20"])).toBe(30);
    expect(fromKobo(sumKobo(["0.10", "0.20"]))).toBe("0.30");
    expect(fromKobo(sumKobo(["1500000.00", "100000.00", "0.01"]))).toBe("1600000.01");
  });

  it("formats in en-NG style with ₦", () => {
    expect(formatKobo(150000000)).toBe("₦1,500,000.00");
    expect(formatKobo(5)).toBe("₦0.05");
    expect(formatKobo(-125005)).toBe("-₦1,250.05");
    expect(formatMoney("1500.5")).toBe("₦1,500.50");
    expect(formatMoney("garbage")).toBe("₦0.00");
  });

  it("normalises what the user typed", () => {
    expect(parseAmountInput("₦1,500.5")).toBe("1500.50");
    expect(parseAmountInput("200")).toBe("200.00");
    expect(parseAmountInput("0")).toBeNull();
    expect(parseAmountInput("1.999")).toBeNull();
    expect(parseAmountInput("-5")).toBeNull();
  });
});

describe("charges grouping and summary", () => {
  const leases = [lease, { ...lease, id: "lease-2", landlord: "Okafor Homes" }] as MyLease[];
  const list = [
    charge({ id: "a", due_date: "2026-11-01", balance: "100.10" }),
    charge({ id: "b", due_date: "2026-09-01", balance: "200.20", is_overdue: true }),
    charge({ id: "c", lease: "lease-2", organization: "org-2", organization_name: "Okafor Homes", due_date: "2026-12-01", balance: "50.00" }),
    charge({ id: "d", lease: null, organization: "org-3", organization_name: "Shop 4 Owner", balance: "10.00" }),
    charge({ id: "e", status: "paid", balance: "0.00" }),
  ] as Charge[];

  it("groups by landlord organization, most urgent first", () => {
    const groups = groupCharges(list, leases);
    expect(groups.map((g) => g.landlord)).toEqual(["Bello Properties", "Shop 4 Owner", "Okafor Homes"]);
    expect(groups[0]!.landlordPhone).toBe("+2348099999999");
    expect(groups[0]!.charges.map((c) => c.id)).toEqual(["b", "a"]); // by due date
    expect(groups[0]!.totalKobo).toBe(30030);
    expect(groups[0]!.overdueKobo).toBe(20020);
  });

  it("summarises total owed, overdue and next due", () => {
    const s = summarise(list);
    expect(s.totals).toEqual([{ currency: "NGN", totalKobo: 36030, overdueKobo: 20020 }]);
    expect(s.overdueCount).toBe(1);
    expect(s.nextDue?.id).toBe("d"); // earliest not-yet-overdue due date (2026-10-01)
  });
});

describe("phone, PIN, dates, idempotency", () => {
  it("normalises Nigerian numbers like the backend", () => {
    for (const raw of ["08012345678", "8012345678", "2348012345678", "+234 801 234 5678"]) {
      expect(normalisePhone(raw)).toBe("+2348012345678");
    }
    expect(isValidPhone("+2348012345678")).toBe(true);
    expect(isValidPhone("0801")).toBe(false);
  });

  it("flags weak PINs like the backend", () => {
    expect(["123456", "654321", "000000"].map(isWeakPin)).toEqual([true, true, true]);
    expect(isWeakPin("739152")).toBe(false);
  });

  it("formats dates in Lagos time", () => {
    expect(formatDate("2026-10-05")).toBe("5 Oct 2026");
    expect(formatDateTime("2026-10-05T13:30:00Z")).toBe("5 Oct 2026, 14:30");
  });

  it("makes idempotency keys the backend accepts", () => {
    const a = newIdempotencyKey();
    expect(a).toMatch(/^[A-Za-z0-9_\-:.]{16,64}$/);
    expect(newIdempotencyKey()).not.toBe(a);
  });
});
