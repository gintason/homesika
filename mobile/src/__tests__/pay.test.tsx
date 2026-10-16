import { act, fireEvent, screen, waitFor } from "@testing-library/react-native";
import { router, useLocalSearchParams } from "expo-router";
import * as WebBrowser from "expo-web-browser";

import Charges from "@/app/(app)/(tabs)/charges";
import Home from "@/app/(app)/(tabs)/index";
import PayResult from "@/app/(app)/pay/[reference]";
import { tokens } from "@/lib/secure";
import { useSession } from "@/store/session";
import { charge, json, lease, mockFetch, page, renderWithClient, type Call } from "@/testing/utils";

const started = { reference: "HSK-REF-1", checkout_url: "https://checkout.paystack.com/abc", gateway: "paystack" };

beforeEach(async () => {
  jest.clearAllMocks();
  await tokens.set("access-1", "refresh-1");
  useSession.setState({ status: "ready", profile: { firstName: "Ada", lastName: "Obi", phone: "+2348012345678" }, lockSuspendedUntil: 0 });
});

function tenantRoutes(extra: (c: Call) => Response | Promise<Response> | undefined, charges = [charge()], leases = [lease]) {
  return (c: Call) => {
    if (c.url.includes("/api/v1/me/leases/")) return json(200, leases);
    if (c.url.includes("/api/v1/me/charges/")) return json(200, page(charges));
    return extra(c);
  };
}

describe("pay flow", () => {
  it("POST /me/pay -> opens checkout -> result screen polls status -> success", async () => {
    const calls = mockFetch(tenantRoutes((c) => (c.url.endsWith("/api/v1/me/pay/") ? json(201, started) : undefined)));
    renderWithClient(<Home />);
    fireEvent.press(await screen.findByRole("button", { name: "Pay ₦1,500,000.00" }));

    await waitFor(() => expect(router.push).toHaveBeenCalled());
    const pay = calls.find((c) => c.url.endsWith("/api/v1/me/pay/"))!;
    expect(pay.method).toBe("POST");
    expect(pay.body).toEqual({ charges: ["c1"] });
    expect(pay.headers.Authorization).toMatch(/^Bearer /);
    expect(pay.headers["Idempotency-Key"]).toMatch(/^pay_[0-9a-f]{32}$/);
    expect(WebBrowser.openBrowserAsync).toHaveBeenCalledWith(started.checkout_url, expect.any(Object));
    expect(useSession.getState().lockSuspendedUntil).toBeGreaterThan(Date.now()); // no lock while in checkout
    expect(router.push).toHaveBeenCalledWith({ pathname: "/pay/[reference]", params: { reference: "HSK-REF-1" } });

    // Result screen: pending, pending, then paid.
    screen.unmount();
    jest.useFakeTimers();
    try {
      const statuses = [
        { status: "pending", receipt_number: null },
        { status: "pending", receipt_number: null },
        { status: "paid", receipt_number: "RCT-2026-0001" },
      ];
      const statusCalls = mockFetch((c) =>
        c.url.endsWith("/api/v1/pay/HSK-REF-1/status/") ? json(200, statuses.shift() ?? { status: "paid", receipt_number: "RCT-2026-0001" }) : json(200, page([])),
      );
      jest.mocked(useLocalSearchParams).mockReturnValue({ reference: "HSK-REF-1" });
      renderWithClient(<PayResult />);
      expect(screen.getByText("Checking your payment")).toBeTruthy();
      await act(async () => {
        await jest.advanceTimersByTimeAsync(6000);
      });
      expect(screen.getByText("Payment received")).toBeTruthy();
      expect(screen.getByText("Receipt RCT-2026-0001")).toBeTruthy();
      const polled = statusCalls.filter((c) => c.url.includes("/status/"));
      expect(polled).toHaveLength(3);
      expect(polled[0]!.headers.Authorization).toBeUndefined(); // public endpoint
      expect(useSession.getState().lockSuspendedUntil).toBe(0);
    } finally {
      jest.useRealTimers();
    }
  });

  it("says 'still processing' (don't pay again) when the bank hasn't confirmed, and can check again", async () => {
    jest.useFakeTimers();
    try {
      const calls = mockFetch(() => json(200, { status: "pending", receipt_number: null }));
      jest.mocked(useLocalSearchParams).mockReturnValue({ reference: "HSK-REF-2" });
      renderWithClient(<PayResult />);
      await act(async () => {
        await jest.advanceTimersByTimeAsync(20000);
      });
      expect(screen.getByText("Still processing")).toBeTruthy();
      expect(screen.getByText(/Don't pay again/)).toBeTruthy();
      expect(calls).toHaveLength(5); // a few tries with backoff, then stop
      fireEvent.press(screen.getByRole("button", { name: "Check again" }));
      expect(screen.getByText("Checking your payment")).toBeTruthy();
      await act(async () => {
        await jest.advanceTimersByTimeAsync(20000);
      });
      expect(screen.getByText("Still processing")).toBeTruthy();
      expect(calls).toHaveLength(10);
    } finally {
      jest.useRealTimers();
    }
  });

  it("reuses the Idempotency-Key when the same submit is retried after a network error", async () => {
    let payAttempts = 0;
    const calls = mockFetch(
      tenantRoutes((c) => {
        if (!c.url.endsWith("/api/v1/me/pay/")) return undefined;
        payAttempts++;
        return payAttempts === 1 ? Promise.reject(new TypeError("Network request failed")) : json(201, started);
      }),
    );
    renderWithClient(<Home />);
    fireEvent.press(await screen.findByRole("button", { name: "Pay ₦1,500,000.00" }));
    expect(await screen.findByText(/No internet connection/)).toBeTruthy();
    expect(WebBrowser.openBrowserAsync).not.toHaveBeenCalled();

    fireEvent.press(screen.getByRole("button", { name: "Pay ₦1,500,000.00" }));
    await waitFor(() => expect(WebBrowser.openBrowserAsync).toHaveBeenCalledTimes(1));
    const keys = calls.filter((c) => c.url.endsWith("/me/pay/")).map((c) => c.headers["Idempotency-Key"]);
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
  });

  it("only lets you select charges from one landlord at a time", async () => {
    const leases = [lease, { ...lease, id: "lease-2", landlord: "Okafor Homes" }];
    const charges = [
      charge({ id: "a", description: "Rent 2026", balance: "1000.00" }),
      charge({ id: "b", lease: "lease-2", organization: "org-2", organization_name: "Okafor Homes", description: "Water bill", balance: "250.00" }),
    ];
    const calls = mockFetch(tenantRoutes((c) => (c.url.endsWith("/me/pay/") ? json(201, started) : undefined), charges, leases));
    renderWithClient(<Charges />);
    fireEvent.press(await screen.findByRole("checkbox", { name: /Select Rent 2026/ }));
    expect(screen.getByRole("button", { name: "Pay ₦1,000.00" })).toBeTruthy();
    fireEvent.press(screen.getByRole("checkbox", { name: /Select Water bill/ }));
    expect(screen.getByText(/You can pay one landlord at a time\. We've switched your selection to Okafor Homes/)).toBeTruthy();
    fireEvent.press(screen.getByRole("button", { name: "Pay ₦250.00" }));
    await waitFor(() => expect(WebBrowser.openBrowserAsync).toHaveBeenCalled());
    expect(calls.find((c) => c.url.endsWith("/me/pay/"))!.body).toEqual({ charges: ["b"] });
  });
});
