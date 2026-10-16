import { tokens } from "../theme/tokens";
import { addYearsMinusDay, formatDate, localInputToISO } from "./dates";
import { getDeviceId } from "./device";
import { can } from "./permissions";
import { formatPhone, isValidNigerianPhone, normalisePhone } from "./phone";
import { isWeakPin } from "./pin";

describe("phone", () => {
  it("normalises Nigerian numbers to E.164", () => {
    expect(normalisePhone("0803 123 4567")).toBe("+2348031234567");
    expect(normalisePhone("2348031234567")).toBe("+2348031234567");
    expect(normalisePhone("+234 803 123 4567")).toBe("+2348031234567");
    expect(normalisePhone("8031234567")).toBe("+2348031234567");
    expect(isValidNigerianPhone("08031234567")).toBe(true);
    expect(isValidNigerianPhone("0803123")).toBe(false);
    expect(formatPhone("+2348031234567")).toBe("0803 123 4567");
  });
});

describe("pin", () => {
  it("matches the API's weak PIN rule", () => {
    expect(isWeakPin("111111")).toBe(true);
    expect(isWeakPin("123456")).toBe(true);
    expect(isWeakPin("654321")).toBe(true);
    expect(isWeakPin("4826")).toBe(false);
    expect(isWeakPin("402913")).toBe(false);
  });
});

describe("dates", () => {
  it("treats date-only values as calendar dates", () => {
    expect(formatDate("2026-01-01")).toMatch(/1 Jan 2026/);
    expect(addYearsMinusDay("2026-01-01", 1)).toBe("2026-12-31");
    expect(localInputToISO("not a date")).toBeNull();
  });
});

describe("device + permissions", () => {
  it("generates a device id that matches the API rule and keeps it", () => {
    const id = getDeviceId();
    expect(id).toMatch(/^[A-Za-z0-9_-]{16,64}$/);
    expect(getDeviceId()).toBe(id);
  });

  it("mirrors the backend capability matrix", () => {
    expect(can("owner", "org.manage")).toBe(true);
    expect(can("manager", "payment.record")).toBe(true);
    expect(can("manager", "members.manage")).toBe(false);
    expect(can("agent", "payment.view")).toBe(false);
    expect(can(null, "org.view")).toBe(false);
  });
});

describe("design tokens", () => {
  it("keeps the brand colours the UI relies on", () => {
    expect(tokens.color.primary[800]).toBe("#0B2B63");
    expect(tokens.color.primary[600]).toBe("#1F4A81");
  });
});
