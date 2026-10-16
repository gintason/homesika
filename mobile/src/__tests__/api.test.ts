import { api, ApiError, errorText, setSessionExpiredHandler } from "@/lib/api";
import { tokens } from "@/lib/secure";
import { json, mockFetch } from "@/testing/utils";

beforeEach(async () => {
  await tokens.set("access-1", "refresh-1");
  setSessionExpiredHandler(() => {});
});

describe("api client", () => {
  it("sends the bearer token, language and Idempotency-Key", async () => {
    const calls = mockFetch(() => json(201, { ok: true }));
    await api("/api/v1/me/pay/", { method: "POST", body: { charges: ["c1"] }, idempotencyKey: "pay_abc123abc123abc1" });
    expect(calls[0]!.headers.Authorization).toBe("Bearer access-1");
    expect(calls[0]!.headers["Idempotency-Key"]).toBe("pay_abc123abc123abc1");
    expect(calls[0]!.headers["Accept-Language"]).toBe("en");
    expect(calls[0]!.url).toBe("http://localhost:8001/api/v1/me/pay/");
  });

  it("maps the error envelope to ApiError with field details", async () => {
    mockFetch(() =>
      json(400, { error: { code: "validation_error", message: "Please check your input.", details: { charges: ["Pay one landlord at a time."] } } }),
    );
    const err = (await api("/x").catch((e) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect([err.status, err.code, err.message, err.fieldMessage("charges")]).toEqual([
      400,
      "validation_error",
      "Please check your input.",
      "Pay one landlord at a time.",
    ]);
    // The user sees the field message, not the generic one.
    expect(errorText(err)).toBe("Pay one landlord at a time.");
  });

  it("uses translated copy for known codes and shows attempts left", async () => {
    mockFetch(() => json(403, { error: { code: "invalid_login_pin", message: "Incorrect PIN.", details: { attempts_left: 2 } } }));
    const err = (await api("/x", { auth: false }).catch((e) => e)) as ApiError;
    expect(err.attemptsLeft).toBe(2);
    expect(errorText(err)).toBe("Incorrect PIN. Attempts left: 2.");
  });

  it("handles a non-JSON error body", async () => {
    mockFetch(() => new Response("<html>Bad gateway</html>", { status: 502 }));
    const err = (await api("/x").catch((e) => e)) as ApiError;
    expect([err.status, err.code]).toEqual([502, "server_error"]);
  });

  it("refreshes ONCE for concurrent 401s, then retries each request", async () => {
    let refreshCalls = 0;
    mockFetch((c) => {
      if (c.url.endsWith("/auth/refresh/")) {
        refreshCalls++;
        return json(200, { access: "access-2", refresh: "refresh-2" });
      }
      return c.headers.Authorization === "Bearer access-2" ? json(200, { ok: true }) : json(401, { error: { code: "token_not_valid" } });
    });
    const results = await Promise.all([api("/a"), api("/b"), api("/c")]);
    expect(results).toEqual([{ ok: true }, { ok: true }, { ok: true }]);
    expect(refreshCalls).toBe(1); // rotation-safe: one refresh shared by all three
    expect(await tokens.get()).toEqual({ access: "access-2", refresh: "refresh-2" });
  });

  it("does not loop: a second 401 after refreshing is returned as an error", async () => {
    let refreshCalls = 0;
    const calls = mockFetch((c) => {
      if (c.url.endsWith("/auth/refresh/")) {
        refreshCalls++;
        return json(200, { access: "access-2" });
      }
      return json(401, { error: { code: "not_authenticated", message: "No." } });
    });
    const err = (await api("/a").catch((e) => e)) as ApiError;
    expect(err.status).toBe(401);
    expect(refreshCalls).toBe(1);
    expect(calls.filter((c) => c.url.endsWith("/a"))).toHaveLength(2);
  });

  it("signals session expiry when the refresh token is rejected", async () => {
    const expired = jest.fn();
    setSessionExpiredHandler(expired);
    mockFetch((c) => (c.url.endsWith("/auth/refresh/") ? json(401, {}) : json(401, { error: { code: "token_not_valid" } })));
    await expect(api("/api/v1/me/")).rejects.toBeInstanceOf(ApiError);
    expect(expired).toHaveBeenCalledTimes(1);
  });

  it("never refreshes for anonymous calls (e.g. pin-login's device_not_recognised 401)", async () => {
    const calls = mockFetch(() => json(401, { error: { code: "device_not_recognised", message: "Please sign in again." } }));
    const err = (await api("/api/v1/auth/pin-login/", { method: "POST", auth: false, body: {} }).catch((e) => e)) as ApiError;
    expect(err.code).toBe("device_not_recognised");
    expect(calls).toHaveLength(1);
    expect(calls[0]!.headers.Authorization).toBeUndefined();
  });

  it("turns network failures into a friendly network_error", async () => {
    mockFetch(() => Promise.reject(new TypeError("Network request failed")));
    const err = (await api("/x").catch((e) => e)) as ApiError;
    expect([err.code, err.status, err.isNetwork]).toEqual(["network_error", 0, true]);
  });

  it("returns undefined for 204", async () => {
    mockFetch(() => new Response(null, { status: 204 }));
    await expect(api("/api/v1/auth/logout/", { method: "POST", body: {} })).resolves.toBeUndefined();
  });
});
