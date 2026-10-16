import { envelope, mockFetch } from "../test/fetch";
import { api, ApiError, apiUrl } from "./api";
import { session } from "./session";

describe("api client", () => {
  it("turns the error envelope into a typed ApiError with field errors", async () => {
    mockFetch({
      "POST /api/v1/auth/register/": envelope(400, "validation_error", "Please check your input.", {
        phone_number: ["An account with this phone number already exists."],
        non_field_errors: ["Something about the whole form."],
      }),
    });
    const err = await api("/auth/register/", { method: "POST", auth: false, body: {} }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    const e = err as ApiError;
    expect(e.status).toBe(400);
    expect(e.code).toBe("validation_error");
    expect(e.fieldErrors.phone_number).toBe("An account with this phone number already exists.");
    expect(e.formErrors).toEqual(["Something about the whole form."]);
    expect(e.summary).toBe("Something about the whole form.");
  });

  it("handles list-shaped validation errors and non-JSON server errors", async () => {
    mockFetch({
      "PATCH /api/v1/orgs/x/leases/1/": envelope(400, "validation_error", "Please check your input.", ["Only notes can change."]),
      "GET /api/v1/boom/": { status: 502, raw: "<html>Bad gateway</html>" },
    });
    const a = (await api("/orgs/x/leases/1/", { method: "PATCH", body: {} }).catch((e: unknown) => e)) as ApiError;
    expect(a.formErrors).toEqual(["Only notes can change."]);
    const b = (await api("/boom/").catch((e: unknown) => e)) as ApiError;
    expect(b.status).toBe(502);
    expect(b.code).toBe("server_error");
  });

  it("reports network failures as ApiError status 0", async () => {
    mockFetch({ "GET /api/v1/me/": new TypeError("Failed to fetch") });
    const e = (await api("/me/").catch((x: unknown) => x)) as ApiError;
    expect(e.status).toBe(0);
    expect(e.code).toBe("network_error");
  });

  it("sends the bearer token, Idempotency-Key and JSON body", async () => {
    session.setTokens({ access: "acc-1", refresh: "ref-1" });
    const m = mockFetch({ "POST /api/v1/orgs/o/payments/manual/": { status: 201, body: { id: "p1" } } });
    await api("/orgs/o/payments/manual/", { method: "POST", body: { amount: "100.00" }, idempotencyKey: "key-1234567890abcdef" });
    const call = m.calls[0]!;
    expect(call.headers.Authorization).toBe("Bearer acc-1");
    expect(call.headers["Idempotency-Key"]).toBe("key-1234567890abcdef");
    expect(call.body).toEqual({ amount: "100.00" });
  });

  it("refreshes once on 401 and retries the request with the new token", async () => {
    session.setTokens({ access: "old", refresh: "ref-old" });
    const m = mockFetch({
      "GET /api/v1/me/": (req) => (req.headers.Authorization === "Bearer new" ? { body: { id: "u1" } } : envelope(401, "token_not_valid", "Expired")),
      "POST /api/v1/auth/refresh/": { body: { access: "new", refresh: "ref-new" } },
    });
    await expect(api("/me/")).resolves.toEqual({ id: "u1" });
    expect(m.find("POST", "/api/v1/auth/refresh/")).toHaveLength(1);
    expect(m.find("POST", "/api/v1/auth/refresh/")[0]!.body).toEqual({ refresh: "ref-old" });
    expect(session.getRefresh()).toBe("ref-new"); // rotated token stored
  });

  it("does not loop when the retried request is still 401", async () => {
    session.setTokens({ access: "old", refresh: "ref" });
    const m = mockFetch({
      "GET /api/v1/me/": envelope(401, "token_not_valid", "Expired"),
      "POST /api/v1/auth/refresh/": { body: { access: "new", refresh: "ref2" } },
    });
    const e = (await api("/me/").catch((x: unknown) => x)) as ApiError;
    expect(e.status).toBe(401);
    expect(m.find("GET", "/api/v1/me/")).toHaveLength(2);
    expect(m.find("POST", "/api/v1/auth/refresh/")).toHaveLength(1);
  });

  it("ends the session when the refresh token is rejected", async () => {
    session.setTokens({ access: "old", refresh: "ref" });
    const expired = vi.fn();
    const off = session.onExpired(expired);
    mockFetch({
      "GET /api/v1/me/": envelope(401, "token_not_valid", "Expired"),
      "POST /api/v1/auth/refresh/": envelope(401, "token_not_valid", "Token is blacklisted"),
    });
    await expect(api("/me/")).rejects.toBeInstanceOf(ApiError);
    expect(expired).toHaveBeenCalledTimes(1);
    expect(session.getRefresh()).toBeNull();
    off();
  });

  it("never refreshes for unauthenticated calls (e.g. pin-login 401 device_not_recognised)", async () => {
    session.setTokens({ access: "a", refresh: "r" });
    const m = mockFetch({
      "POST /api/v1/auth/pin-login/": envelope(401, "device_not_recognised", "Please sign in again on this device."),
    });
    const e = (await api("/auth/pin-login/", { method: "POST", auth: false, body: {} }).catch((x: unknown) => x)) as ApiError;
    expect(e.code).toBe("device_not_recognised");
    expect(m.calls).toHaveLength(1);
  });

  it("builds URLs with query params, skipping empty values", () => {
    expect(apiUrl("/orgs/o/charges/", { status: "outstanding", overdue: true, lease: "", tenant: undefined })).toBe(
      "/api/v1/orgs/o/charges/?status=outstanding&overdue=1",
    );
    expect(apiUrl("https://api.example.com/api/v1/orgs/o/charges/?cursor=abc")).toBe(
      "https://api.example.com/api/v1/orgs/o/charges/?cursor=abc",
    );
  });
});
