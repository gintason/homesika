import { act, fireEvent, screen, waitFor } from "@testing-library/react-native";
import { File } from "expo-file-system";
import { router, useLocalSearchParams } from "expo-router";
import * as WebBrowser from "expo-web-browser";

import BillForm from "@/app/(app)/bills/[category]";
import BillHistory from "@/app/(app)/bills/history";
import BillsHome from "@/app/(app)/bills/index";
import BillOrderScreen from "@/app/(app)/bills/order/[id]";
import Home from "@/app/(app)/(tabs)/index";
import { copyText } from "@/lib/clipboard";
import { formatToken, matchDisco, parseNairaAmount } from "@/lib/bills";
import { tokens } from "@/lib/secure";
import { useSession } from "@/store/session";
import { json, lease, mockFetch, page, renderWithClient, type Call } from "@/testing/utils";

jest.mock("@/lib/clipboard", () => ({ copyText: jest.fn(async () => "copied") }));

const plan = (id: string, code: string, name: string, price: string | null, validity_days: number | null = null) => ({
  id,
  code,
  name,
  price,
  validity_days,
  data_mb: null,
});

const biller = (o: Record<string, unknown>) => ({
  customer_label: "Phone number",
  requires_verification: false,
  min_amount: null,
  max_amount: null,
  plans: [],
  ...o,
});

const airtime = [
  biller({ id: "b-mtn-a", category: "airtime", code: "mtn", name: "MTN airtime", min_amount: "100.00", max_amount: "50000.00" }),
  biller({ id: "b-glo-a", category: "airtime", code: "glo", name: "Glo airtime", min_amount: "100.00", max_amount: "50000.00" }),
];

const data = [
  biller({
    id: "b-mtn-d",
    category: "data",
    code: "mtn",
    name: "MTN data",
    plans: [plan("p-1gb", "vtung-1", "1GB", "1000.00", 30), plan("p-5gb", "vtung-5", "5GB", "4000.00", 30)],
  }),
  biller({ id: "b-glo-d", category: "data", code: "glo", name: "Glo data", plans: [plan("p-g1", "vtung-g1", "Glo 2GB", "1000.00", 1)] }),
];

const tv = [
  biller({
    id: "b-dstv",
    category: "cable_tv",
    code: "dstv",
    name: "DStv",
    customer_label: "Smartcard / IUC number",
    requires_verification: true,
    fee: "100.00",
    plans: [plan("p-compact", "vtung-c", "Compact", "15700.00", 30)],
  }),
];

const discoPlans = (k: string) => [plan(`${k}-pre`, "prepaid", "Prepaid", null), plan(`${k}-post`, "postpaid", "Postpaid", null)];
const electricity = [
  biller({
    id: "b-eko",
    category: "electricity",
    code: "eko-electric",
    name: "Eko Electric (EKEDC)",
    customer_label: "Meter number",
    requires_verification: true,
    min_amount: "1000.00",
    max_amount: "200000.00",
    plans: discoPlans("eko"),
  }),
  biller({
    id: "b-ikeja",
    category: "electricity",
    code: "ikeja-electric",
    name: "Ikeja Electric (IKEDC)",
    customer_label: "Meter number",
    requires_verification: true,
    min_amount: "1000.00",
    max_amount: "200000.00",
    plans: discoPlans("ike"),
  }),
];

const myLease = { ...lease, unit: "unit-1", meter_number: "45012345678", disco: "Ikeja Electric" };

function order(o: Record<string, unknown> = {}) {
  return {
    id: "o1",
    reference: "BIL0123456789ABCDEF",
    category: "electricity",
    biller: "b-ikeja",
    biller_name: "Ikeja Electric (IKEDC)",
    plan: "ike-pre",
    plan_name: "Prepaid",
    customer_id: "45012345678",
    customer_name: "ADA OBI",
    amount: "5000.00",
    fee: "0.00",
    total: "5000.00",
    currency: "NGN",
    status: "awaiting_payment",
    checkout_url: "https://checkout.paystack.com/bill1",
    token: "",
    units: "",
    receipt_number: "",
    failure_reason: "",
    created_at: "2026-10-17T09:00:00Z",
    paid_at: null,
    delivered_at: null,
    refunded_at: null,
    expires_at: "2099-01-01T00:00:00Z",
    ...o,
  };
}

const catalogue = (c: Call) => {
  const m = /\/api\/v1\/bills\/catalogue\/\?category=(\w+)/.exec(c.url);
  if (!m) return undefined;
  const all: Record<string, unknown[]> = { airtime, data, cable_tv: tv, electricity };
  return json(200, all[m[1]!] ?? []);
};

beforeEach(async () => {
  jest.clearAllMocks();
  await tokens.set("access-1", "refresh-1");
  useSession.setState({
    status: "ready",
    profile: { firstName: "Ada", lastName: "Obi", phone: "+2348012345678" },
    lockSuspendedUntil: 0,
  });
});

function renderForm(category: string) {
  jest.mocked(useLocalSearchParams).mockReturnValue({ category });
  return renderWithClient(<BillForm />);
}

describe("bills: catalogue and forms", () => {
  it("loads the public catalogue, lets me pick a data plan, and pays the plan price (no amount sent)", async () => {
    const calls = mockFetch((c) => catalogue(c) ?? (c.url.endsWith("/api/v1/bills/orders/") ? json(201, order({ category: "data", total: "1000.00", amount: "1000.00" })) : undefined));
    renderForm("data");

    expect(await screen.findByRole("radio", { name: "MTN data" })).toBeTruthy();
    const get = calls.find((c) => c.url.includes("/bills/catalogue/"))!;
    expect(get.url).toMatch(/\?category=data$/);
    expect(get.headers.Authorization).toBeUndefined(); // public
    expect(screen.getByDisplayValue("8012345678")).toBeTruthy(); // my number, prefilled

    // Two networks: nothing chosen until I pick one; then its plans show with price and validity.
    fireEvent.press(screen.getByRole("radio", { name: "MTN data" }));
    expect(screen.getAllByText("Lasts 30 days")).toHaveLength(2);
    fireEvent.press(screen.getByRole("radio", { name: "5GB, ₦4,000.00, Lasts 30 days" }));
    expect(screen.getByRole("radio", { name: "5GB, ₦4,000.00, Lasts 30 days", selected: true })).toBeTruthy();
    fireEvent.press(screen.getByRole("radio", { name: "1GB, ₦1,000.00, Lasts 30 days" }));

    fireEvent.press(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByText("Check and pay")).toBeTruthy();
    expect(screen.getByText("MTN data · 1GB")).toBeTruthy();
    expect(screen.getByText("+234 801 234 5678")).toBeTruthy();
    expect(screen.getByText(/no wallet or balance/)).toBeTruthy();

    fireEvent.press(screen.getByRole("button", { name: "Pay ₦1,000.00" }));
    await waitFor(() => expect(WebBrowser.openBrowserAsync).toHaveBeenCalled());
    const post = calls.find((c) => c.method === "POST")!;
    expect(post.body).toEqual({ biller: "b-mtn-d", plan: "p-1gb", customer_id: "+2348012345678" });
    expect(router.replace).toHaveBeenCalledWith({ pathname: "/bills/order/[id]", params: { id: "o1" } });
  });

  it("electricity: prefills my meter and DisCo, shows the verified name, sends unit, reuses the key on retry", async () => {
    let posts = 0;
    const calls = mockFetch((c) => {
      if (c.url.includes("/api/v1/me/leases/")) return json(200, [myLease]);
      if (c.url.endsWith("/api/v1/bills/verify/"))
        return json(200, { customer_id: "45012345678", name: "ADA OBI", details: { customer_address: "12 Allen Avenue" } });
      if (c.url.endsWith("/api/v1/bills/orders/")) {
        posts++;
        return posts === 1 ? Promise.reject(new TypeError("Network request failed")) : json(201, order());
      }
      return catalogue(c);
    });
    renderForm("electricity");

    expect(await screen.findByDisplayValue("45012345678")).toBeTruthy();
    expect(screen.getByRole("radio", { name: "Ikeja Electric (IKEDC)", selected: true })).toBeTruthy(); // "Ikeja Electric" matched
    expect(screen.getByRole("radio", { name: "Prepaid", selected: true })).toBeTruthy();
    expect(screen.getByText(/Your meter at Palm Court · Flat 2/)).toBeTruthy();

    fireEvent.press(screen.getByRole("button", { name: "Check meter number" }));
    expect(await screen.findByText(/Name: ADA OBI/)).toBeTruthy();
    expect(screen.getByText(/Address: 12 Allen Avenue/)).toBeTruthy();
    const verify = calls.find((c) => c.url.endsWith("/bills/verify/"))!;
    expect(verify.body).toEqual({ biller: "b-ikeja", customer_id: "45012345678", plan: "ike-pre" });
    expect(verify.headers.Authorization).toBe("Bearer access-1");

    fireEvent.changeText(screen.getByLabelText("Amount"), "5000");
    fireEvent.press(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByText("Check and pay")).toBeTruthy();
    expect(screen.getByText("ADA OBI")).toBeTruthy();
    expect(screen.getByText("Ikeja Electric (IKEDC) · Prepaid")).toBeTruthy();

    fireEvent.press(screen.getByRole("button", { name: "Pay ₦5,000.00" }));
    expect(await screen.findByText(/No internet connection/)).toBeTruthy();
    expect(WebBrowser.openBrowserAsync).not.toHaveBeenCalled();

    fireEvent.press(screen.getByRole("button", { name: "Pay ₦5,000.00" }));
    await waitFor(() => expect(WebBrowser.openBrowserAsync).toHaveBeenCalledWith("https://checkout.paystack.com/bill1", expect.any(Object)));
    const orderPosts = calls.filter((c) => c.url.endsWith("/bills/orders/"));
    expect(orderPosts).toHaveLength(2);
    expect(orderPosts[0]!.body).toEqual({
      biller: "b-ikeja",
      plan: "ike-pre",
      customer_id: "45012345678",
      amount: "5000.00",
      unit: "unit-1",
    });
    const keys = orderPosts.map((c) => c.headers["Idempotency-Key"]);
    expect(keys[0]).toMatch(/^bill_[0-9a-f]{32}$/);
    expect(keys[1]).toBe(keys[0]);
    expect(useSession.getState().lockSuspendedUntil).toBeGreaterThan(Date.now()); // no app lock in checkout
  });

  it("doesn't send my unit when I pay for a different meter", async () => {
    const calls = mockFetch((c) => {
      if (c.url.includes("/api/v1/me/leases/")) return json(200, [myLease]);
      if (c.url.endsWith("/bills/verify/")) return json(200, { customer_id: "99998888777", name: "MAMA T", details: {} });
      if (c.url.endsWith("/bills/orders/")) return json(201, order());
      return catalogue(c);
    });
    renderForm("electricity");
    fireEvent.changeText(await screen.findByDisplayValue("45012345678"), "99998888777");
    fireEvent.changeText(screen.getByLabelText("Amount"), "2000");
    fireEvent.press(screen.getByRole("button", { name: "Continue" })); // verifies, then reviews
    expect(await screen.findByText("MAMA T")).toBeTruthy();
    fireEvent.press(screen.getByRole("button", { name: "Pay ₦2,000.00" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/bills/orders/"))).toBe(true));
    expect(calls.find((c) => c.url.endsWith("/bills/orders/"))!.body).not.toHaveProperty("unit");
  });

  it("lets me choose the DisCo when my unit's DisCo doesn't match one", async () => {
    mockFetch((c) => (c.url.includes("/me/leases/") ? json(200, [{ ...myLease, disco: "Mars Power" }]) : catalogue(c)));
    renderForm("electricity");
    expect(await screen.findByText(/couldn't tell which electricity company/)).toBeTruthy();
    expect(screen.queryByRole("radio", { selected: true, name: /Electric/ })).toBeNull();
    fireEvent.press(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByText("Choose your electricity company.")).toBeTruthy();
  });

  it("shows customer_not_found under the smartcard field and stays on the form", async () => {
    mockFetch((c) =>
      c.url.endsWith("/bills/verify/")
        ? json(400, { error: { code: "customer_not_found", message: "We couldn't find that meter or smartcard number.", details: {} } })
        : catalogue(c),
    );
    renderForm("cable_tv");
    fireEvent.changeText(await screen.findByLabelText("Smartcard / IUC number"), "7012345678");
    fireEvent.press(screen.getByRole("button", { name: "Check smartcard number" }));
    expect(await screen.findByText("We couldn't find that meter or smartcard number. Check it and try again.")).toBeTruthy();
    fireEvent.press(screen.getByRole("radio", { name: /Compact/ }));
    fireEvent.press(screen.getByRole("button", { name: "Continue" }));
    await waitFor(() => expect(screen.queryByText("Check and pay")).toBeNull());
  });

  it("airtime: whole naira only, within the network's min/max, with quick amounts", async () => {
    const calls = mockFetch((c) => catalogue(c) ?? (c.url.endsWith("/bills/orders/") ? json(201, order({ total: "500.00" })) : undefined));
    renderForm("airtime");
    fireEvent.press(await screen.findByRole("radio", { name: "Glo airtime" }));
    const amount = screen.getByLabelText("Amount");

    fireEvent.changeText(amount, "150.50");
    expect(screen.getByText("Enter a whole naira amount (no kobo).")).toBeTruthy();
    fireEvent.changeText(amount, "50");
    expect(screen.getByText("The minimum is ₦100.00.")).toBeTruthy();
    fireEvent.changeText(amount, "60000");
    expect(screen.getByText("The maximum is ₦50,000.00.")).toBeTruthy();
    fireEvent.press(screen.getByRole("button", { name: "Continue" }));
    expect(screen.queryByText("Check and pay")).toBeNull();

    for (const chip of ["₦100", "₦200", "₦500", "₦1,000"]) expect(screen.getByRole("radio", { name: chip })).toBeTruthy();
    fireEvent.press(screen.getByRole("radio", { name: "₦500" }));
    expect(screen.getByDisplayValue("500")).toBeTruthy();
    fireEvent.press(screen.getByRole("button", { name: "Continue" }));
    fireEvent.press(await screen.findByRole("button", { name: "Pay ₦500.00" }));
    await waitFor(() => expect(WebBrowser.openBrowserAsync).toHaveBeenCalled());
    expect(calls.find((c) => c.method === "POST")!.body).toEqual({ biller: "b-glo-a", customer_id: "+2348012345678", amount: "500.00" });
  });

  it("shows amount + fee = total and asks again before checkout when a fee applies", async () => {
    const calls = mockFetch(
      (c) => catalogue(c) ?? (c.url.endsWith("/bills/orders/") ? json(201, order({ amount: "500.00", fee: "100.00", total: "600.00" })) : undefined),
    );
    renderForm("airtime");
    fireEvent.press(await screen.findByRole("radio", { name: "MTN airtime" }));
    fireEvent.changeText(screen.getByLabelText("Amount"), "500");
    fireEvent.press(screen.getByRole("button", { name: "Continue" }));
    fireEvent.press(await screen.findByRole("button", { name: "Pay ₦500.00" }));
    expect(await screen.findByRole("button", { name: "Pay ₦600.00" })).toBeTruthy();
    expect(screen.getByText(/A service fee of ₦100.00 applies, so you'll pay ₦600.00/)).toBeTruthy();
    expect(WebBrowser.openBrowserAsync).not.toHaveBeenCalled();
    fireEvent.press(screen.getByRole("button", { name: "Pay ₦600.00" }));
    await waitFor(() => expect(WebBrowser.openBrowserAsync).toHaveBeenCalledTimes(1));
    expect(calls.filter((c) => c.method === "POST")).toHaveLength(1); // the same order, not a new one
  });

  it("shows the catalogue fee up front and goes straight to checkout when the total matches", async () => {
    const calls = mockFetch((c) => {
      if (c.url.endsWith("/bills/verify/")) return json(200, { customer_id: "7012345678", name: "ADA OBI", details: {} });
      if (c.url.endsWith("/bills/orders/"))
        return json(201, order({ category: "cable_tv", amount: "15700.00", fee: "100.00", total: "15800.00" }));
      return catalogue(c);
    });
    renderForm("cable_tv");
    fireEvent.changeText(await screen.findByLabelText("Smartcard / IUC number"), "7012345678");
    fireEvent.press(screen.getByRole("button", { name: "Check smartcard number" }));
    expect(await screen.findByText(/ADA OBI/)).toBeTruthy();
    fireEvent.press(screen.getByRole("radio", { name: /Compact/ }));
    fireEvent.press(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByText("₦100.00")).toBeTruthy(); // the fee row, before any order exists
    fireEvent.press(screen.getByRole("button", { name: "Pay ₦15,800.00" }));
    await waitFor(() => expect(WebBrowser.openBrowserAsync).toHaveBeenCalledTimes(1)); // no second ask
    expect(screen.queryByText(/A service fee of/)).toBeNull();
    expect(calls.filter((c) => c.method === "POST" && c.url.endsWith("/bills/orders/"))).toHaveLength(1);
  });

  it("explains a daily limit error", async () => {
    mockFetch(
      (c) =>
        catalogue(c) ??
        (c.url.endsWith("/bills/orders/") ? json(409, { error: { code: "bills_daily_limit", message: "limit", details: {} } }) : undefined),
    );
    renderForm("airtime");
    fireEvent.press(await screen.findByRole("radio", { name: "MTN airtime" }));
    fireEvent.press(screen.getByRole("radio", { name: "₦1,000" }));
    fireEvent.press(screen.getByRole("button", { name: "Continue" }));
    fireEvent.press(await screen.findByRole("button", { name: "Pay ₦1,000.00" }));
    expect(await screen.findByText(/today's limit for bill payments/)).toBeTruthy();
  });
});

describe("bills: order status", () => {
  function renderOrder(id = "o1") {
    jest.mocked(useLocalSearchParams).mockReturnValue({ id });
    return renderWithClient(<BillOrderScreen />);
  }

  it("polls with backoff until delivered, then shows the big token with copy, units and receipt", async () => {
    jest.useFakeTimers();
    try {
      const answers = [
        order(),
        order({ status: "processing", paid_at: "2026-10-17T09:01:00Z" }),
        order({ status: "delivered", token: "12345678901234567890", units: "45.3 kWh", receipt_number: "BIL-000001" }),
      ];
      const calls = mockFetch((c) =>
        c.url.endsWith("/api/v1/bills/orders/o1/") ? json(200, answers.length > 1 ? answers.shift() : answers[0]) : json(200, page([])),
      );
      useSession.setState({ lockSuspendedUntil: Date.now() + 60_000 });
      renderOrder();
      await act(async () => {
        await jest.advanceTimersByTimeAsync(10);
      });
      expect(screen.getByText("Waiting for your payment")).toBeTruthy();
      expect(useSession.getState().lockSuspendedUntil).toBeGreaterThan(0); // still in checkout
      await act(async () => {
        await jest.advanceTimersByTimeAsync(2100);
      });
      expect(screen.getByText("Paid. Delivering now")).toBeTruthy();
      expect(screen.getByText(/Don't pay again/)).toBeTruthy();
      expect(useSession.getState().lockSuspendedUntil).toBe(0);
      await act(async () => {
        await jest.advanceTimersByTimeAsync(60_000);
      });
      expect(screen.getAllByText("Delivered")).toHaveLength(2); // title and badge
      expect(screen.getByText("1234 5678 9012 3456 7890")).toBeTruthy();
      expect(screen.getByText("Units: 45.3 kWh")).toBeTruthy();
      expect(screen.getByText("BIL-000001")).toBeTruthy();
      const polls = calls.filter((c) => c.url.endsWith("/bills/orders/o1/"));
      expect(polls).toHaveLength(3); // stops once delivered
      expect(polls[0]!.headers.Authorization).toBe("Bearer access-1");

      await act(async () => {
        fireEvent.press(screen.getByRole("button", { name: "Copy token" }));
      });
      expect(copyText).toHaveBeenCalledWith("12345678901234567890");
      expect(screen.getByRole("button", { name: "Copied" })).toBeTruthy();
    } finally {
      jest.useRealTimers();
    }
  });

  it("downloads the receipt for a delivered order", async () => {
    mockFetch(() =>
      json(200, order({ status: "delivered", category: "airtime", customer_id: "08012345678", customer_name: "", receipt_number: "BIL-000002" })),
    );
    renderOrder();
    expect(await screen.findAllByText("Delivered")).toHaveLength(2);
    expect(screen.queryByTestId("token-card")).toBeNull(); // no token for airtime
    expect(screen.getAllByText(/\+234 801 234 5678/).length).toBeGreaterThan(0);
    fireEvent.press(screen.getByRole("button", { name: "Download receipt" }));
    await waitFor(() => expect(File.downloadFileAsync).toHaveBeenCalled());
    expect(jest.mocked(File.downloadFileAsync).mock.calls[0]![0]).toMatch(/\/api\/v1\/bills\/orders\/o1\/receipt\/$/);
  });

  it("explains a refund goes back to the card or account in 1–5 working days", async () => {
    mockFetch(() => json(200, order({ status: "refunded", total: "5100.00", refunded_at: "2026-10-17T10:00:00Z" })));
    renderOrder();
    expect(await screen.findAllByText("Refunded")).toHaveLength(2); // title and badge
    expect(screen.getByText(/we refunded ₦5,100.00 to the card or account you paid with\. Refunds usually arrive in 1–5 working days/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Check again" })).toBeNull();
  });

  it("refund pending and expired say what happens", async () => {
    mockFetch(() => json(200, order({ status: "refund_pending" })));
    const { unmount } = renderOrder();
    expect(await screen.findByText("We couldn't deliver this")).toBeTruthy();
    expect(screen.getByText(/We're refunding ₦5,000.00 to the card or account you paid with/)).toBeTruthy();
    unmount();

    mockFetch(() => json(200, order({ status: "expired" })));
    renderOrder();
    expect(await screen.findByText("Payment not completed")).toBeTruthy();
    expect(screen.getByText(/you weren't charged/)).toBeTruthy();
    fireEvent.press(screen.getByRole("button", { name: "Buy again" }));
    expect(router.replace).toHaveBeenCalledWith({ pathname: "/bills/[category]", params: { category: "electricity" } });
  });
});

describe("bills: history and hub", () => {
  it("lists my bill orders with status badges and opens one", async () => {
    const calls = mockFetch((c) =>
      c.url.endsWith("/api/v1/bills/orders/")
        ? json(
            200,
            page([
              order({ id: "o1", status: "delivered" }),
              order({ id: "o2", category: "data", biller_name: "MTN data", plan_name: "1GB", status: "refunded", total: "1000.00" }),
            ]),
          )
        : undefined,
    );
    renderWithClient(<BillHistory />);
    expect(await screen.findByText("Ikeja Electric (IKEDC)")).toBeTruthy();
    expect(screen.getByText("MTN data · 1GB")).toBeTruthy();
    expect(screen.getByText("Delivered")).toBeTruthy();
    expect(screen.getByText("Refunded")).toBeTruthy();
    expect(screen.getByText("₦1,000.00")).toBeTruthy();
    expect(calls[0]!.headers.Authorization).toBe("Bearer access-1");
    fireEvent.press(screen.getByRole("button", { name: /MTN data · 1GB, ₦1,000.00, Refunded/ }));
    expect(router.push).toHaveBeenCalledWith({ pathname: "/bills/order/[id]", params: { id: "o2" } });
  });

  it("shows an empty state", async () => {
    mockFetch(() => json(200, page([])));
    renderWithClient(<BillHistory />);
    expect(await screen.findByText("No bill payments yet")).toBeTruthy();
  });

  it("renders in Pidgin", async () => {
    await act(() => useSession.getState().setLanguage("pcm"));
    try {
      renderWithClient(<BillsHome />);
      expect(screen.getByText("Wetin you wan pay for?")).toBeTruthy();
      expect(screen.getByRole("button", { name: "Light" })).toBeTruthy();
      expect(screen.getByText(/No wallet, no balance to load/)).toBeTruthy();

      mockFetch(() => json(200, order({ status: "refunded" })));
      jest.mocked(useLocalSearchParams).mockReturnValue({ id: "o1" });
      renderWithClient(<BillOrderScreen />);
      expect(await screen.findAllByText("Money don return")).toHaveLength(2);
      expect(screen.getByText(/1–5 working days, depend on your bank/)).toBeTruthy();
    } finally {
      await act(() => useSession.getState().setLanguage("en"));
    }
  });

  it("Home has a Bills card (the tab bar is full) that opens a category and history", async () => {
    mockFetch((c) => (c.url.includes("/leases/") ? json(200, []) : json(200, page([]))));
    renderWithClient(<Home />);
    expect(await screen.findByText("Nothing to show yet")).toBeTruthy();
    expect(screen.getByText("Pay bills")).toBeTruthy();
    fireEvent.press(screen.getByRole("button", { name: "Airtime" }));
    expect(router.push).toHaveBeenCalledWith({ pathname: "/bills/[category]", params: { category: "airtime" } });
    fireEvent.press(screen.getByRole("button", { name: "My bill payments" }));
    expect(router.push).toHaveBeenCalledWith("/bills/history");
  });

  it("hub tiles open each category", () => {
    renderWithClient(<BillsHome />);
    fireEvent.press(screen.getByRole("button", { name: "Electricity" }));
    expect(router.push).toHaveBeenCalledWith({ pathname: "/bills/[category]", params: { category: "electricity" } });
  });
});

describe("bills helpers", () => {
  it("matches a unit's DisCo by name, code or abbreviation, case-insensitively", () => {
    const billers = electricity as unknown as Parameters<typeof matchDisco>[0];
    expect(matchDisco(billers, "Ikeja Electric")?.id).toBe("b-ikeja");
    expect(matchDisco(billers, "ikeja-electric")?.id).toBe("b-ikeja");
    expect(matchDisco(billers, "EKEDC")?.id).toBe("b-eko");
    expect(matchDisco(billers, "eko electric (ekedc)")?.id).toBe("b-eko");
    expect(matchDisco(billers, "Mars Power")).toBeNull();
    expect(matchDisco(billers, "")).toBeNull();
  });

  it("parses whole-naira amounts", () => {
    const limits = { min_amount: "100.00", max_amount: "50000.00" };
    expect(parseNairaAmount("1,500", limits)).toEqual({ amount: "1500.00" });
    expect(parseNairaAmount("₦ 200.00", limits)).toEqual({ amount: "200.00" });
    expect(parseNairaAmount("200.5", limits)).toEqual({ error: "whole" });
    expect(parseNairaAmount("abc", limits)).toEqual({ error: "invalid" });
    expect(parseNairaAmount("", limits)).toEqual({ error: "required" });
    expect(parseNairaAmount("99", limits)).toEqual({ error: "min" });
    expect(parseNairaAmount("50001", limits)).toEqual({ error: "max" });
  });

  it("groups a token in fours", () => {
    expect(formatToken("12345678901234567890")).toBe("1234 5678 9012 3456 7890");
    expect(formatToken("TOKEN-ABC")).toBe("TOKEN-ABC");
  });
});
