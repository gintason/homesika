import { fireEvent, screen, waitFor } from "@testing-library/react-native";
import { router } from "expo-router";
import * as WebBrowser from "expo-web-browser";

import AirtimeAbroad from "@/app/(app)/bills/abroad";
import { tokens } from "@/lib/secure";
import { json, mockFetch, renderWithClient } from "@/testing/utils";

const lookup = {
  phone: "+233241234567",
  operator: {
    operator_id: "900001", name: "MTN Ghana (sample)", country: "GH", denomination: "range", min_amount: "500.00",
    max_amount: "50000.00", fixed_amounts: [], local_currency: "GHS", fx_rate: 0.0075, sample: true,
  },
};

beforeEach(async () => {
  jest.clearAllMocks();
  await tokens.set("access-1", "refresh-1");
});

describe("airtime abroad", () => {
  it("finds the network from the number, shows an estimate and pays", async () => {
    const calls = mockFetch((c) => {
      if (c.url.endsWith("/bills/intl/countries/")) return json(200, [{ code: "GH", name: "Ghana", currency: "GHS", calling_code: "+233" }]);
      if (c.url.endsWith("/bills/intl/lookup/")) return json(200, lookup);
      if (c.url.endsWith("/bills/intl/orders/"))
        return json(201, { id: "o1", checkout_url: "https://checkout.paystack.com/x", total: "5000.00" });
      return undefined;
    });
    renderWithClient(<AirtimeAbroad />);
    fireEvent.press(await screen.findByRole("radio", { name: "Ghana" }));
    fireEvent.changeText(screen.getByLabelText("Their phone number"), "024 123 4567");
    fireEvent.press(screen.getByRole("button", { name: "Find network" }));
    expect(await screen.findByText("Network: MTN Ghana (sample)")).toBeTruthy();
    expect(screen.getByText(/SAMPLE network data/)).toBeTruthy();
    fireEvent.changeText(screen.getByLabelText("Amount in naira"), "5000");
    expect(screen.getByText(/About 37.50 GHS \(estimate/)).toBeTruthy();
    fireEvent.press(screen.getByRole("button", { name: "Pay ₦5,000.00" }));
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith({ pathname: "/bills/order/[id]", params: { id: "o1" } }));
    expect(WebBrowser.openBrowserAsync).toHaveBeenCalled();
    const order = calls.find((c) => c.url.endsWith("/bills/intl/orders/"))!;
    expect(order.body).toEqual({ country: "GH", phone: "+233241234567", amount: "5000" });
    expect(order.headers["Idempotency-Key"]).toMatch(/^intl_/);
  });

  it("says when it isn't available", async () => {
    mockFetch((c) =>
      c.url.endsWith("/bills/intl/countries/") ? json(503, { error: { code: "intl_unavailable", message: "x", details: {} } }) : undefined,
    );
    renderWithClient(<AirtimeAbroad />);
    expect(await screen.findByText("Airtime abroad isn't available right now.")).toBeTruthy();
  });
});
