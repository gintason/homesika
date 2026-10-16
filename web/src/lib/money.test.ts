import { compareMoney, formatMoney, formatPlainAmount, fromMinor, isPositive, parseMoneyInput, sumMoney, toMinor } from "./money";

describe("money", () => {
  it("formats API decimal strings as naira", () => {
    expect(formatMoney("1500000.00")).toMatch(/^₦\s?1,500,000\.00$/);
    expect(formatMoney("0.5")).toMatch(/₦\s?0\.50/);
    expect(formatMoney(null)).toBe("—");
  });

  it("parses what people type into API strings", () => {
    expect(parseMoneyInput("1,500,000")).toBe("1500000.00");
    expect(parseMoneyInput("₦ 2500.5")).toBe("2500.50");
    expect(parseMoneyInput("250.")).toBe("250.00");
    expect(parseMoneyInput("12.345")).toBeNull();
    expect(parseMoneyInput("abc")).toBeNull();
    expect(parseMoneyInput("1.2.3")).toBeNull();
    expect(parseMoneyInput("")).toBeNull();
  });

  it("does exact arithmetic without floats", () => {
    expect(sumMoney(["0.10", "0.20"])).toBe("0.30");
    expect(sumMoney(["9999999999999.99", "0.01"])).toBe("10000000000000.00");
    expect(toMinor("1500.5")).toBe(150050n);
    expect(fromMinor(-150n)).toBe("-1.50");
    expect(compareMoney("100.00", "99.99")).toBe(1);
    expect(isPositive("0.00")).toBe(false);
    expect(isPositive("0.01")).toBe(true);
  });

  it("shows a typed amount back with separators", () => {
    expect(formatPlainAmount("1500000.5")).toBe("1,500,000.50");
    expect(formatPlainAmount("oops")).toBe("oops");
  });
});
