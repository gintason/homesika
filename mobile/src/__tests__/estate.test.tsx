import { act, fireEvent, screen, waitFor } from "@testing-library/react-native";
import * as Haptics from "expo-haptics";
import { router, useLocalSearchParams } from "expo-router";
import { Alert } from "react-native";

import { ApiError } from "@/lib/api";
import AlertScreen from "@/app/(app)/alert/[id]";
import EstateHome from "@/app/(app)/estate/index";
import JoinEstate from "@/app/(app)/estate/join";
import NewGatePass from "@/app/(app)/estate/pass";
import { HOLD_MS, sendAlert } from "@/lib/panic";
import { setSecure, tokens } from "@/lib/secure";
import { json, mockFetch, page, renderWithClient, type Call } from "@/testing/utils";

const member = (o: Record<string, unknown> = {}) => ({
  id: "m1",
  estate_id: "es1",
  estate_name: "Palm Grove Estate",
  address: "1 Palm Ave",
  organization: "org-1",
  panic_enabled: true,
  house: "A1",
  role: "resident",
  status: "approved",
  dues_outstanding: "15000.00",
  ...o,
});

const myAlert = (o: Record<string, unknown> = {}) => ({
  id: "al1",
  estate: "es1",
  estate_name: "Palm Grove Estate",
  kind: "help",
  status: "triggered",
  silent: false,
  created_at: "2026-10-15T09:00:00Z",
  acknowledged_at: null,
  responding_at: null,
  closed_at: null,
  ...o,
});

function estateRoutes(alerts: unknown[] = [], extra: (c: Call) => Response | undefined = () => undefined) {
  return mockFetch((c) => {
    const special = extra(c);
    if (special) return special;
    if (c.url.endsWith("/me/estates/")) return json(200, page([member()]));
    if (c.url.includes("/me/estates/announcements/")) return json(200, [{ id: "n1", estate: "es1", title: "Water off", body: "Saturday 9-1", audience: "all", urgent: false, created_at: "2026-10-15T08:00:00Z" }]);
    if (c.url.includes("/me/gate-passes/")) return json(200, page([]));
    if (c.url.endsWith("/me/alerts/") && c.method === "GET") return json(200, page(alerts));
    return undefined;
  });
}

beforeEach(async () => {
  jest.clearAllMocks();
  jest.useRealTimers();
  await tokens.set("access-1", "refresh-1");
  await setSecure("panicLocation", "0");
});

describe("estate home", () => {
  it("shows dues, news and the panic button for a verified resident", async () => {
    estateRoutes();
    renderWithClient(<EstateHome />);
    expect(await screen.findByLabelText("Emergency alert")).toBeTruthy();
    expect(await screen.findByText("Water off")).toBeTruthy();
    expect(screen.getByText("₦15,000.00")).toBeTruthy();
    fireEvent.press(screen.getByRole("button", { name: "New gate pass" }));
    expect(router.push).toHaveBeenCalledWith({ pathname: "/estate/pass", params: { estate: "es1" } });
  });

  it("asks people who aren't members to join, and shows waiting approval", async () => {
    mockFetch((c) => (c.url.endsWith("/me/estates/") ? json(200, page([])) : undefined));
    const view = renderWithClient(<EstateHome />);
    fireEvent.press(await screen.findByRole("button", { name: "Join your estate" }));
    expect(router.push).toHaveBeenCalledWith("/estate/join");
    view.unmount();
    mockFetch((c) => (c.url.endsWith("/me/estates/") ? json(200, page([member({ status: "pending" })])) : undefined));
    renderWithClient(<EstateHome />);
    expect(await screen.findByText("Waiting for approval")).toBeTruthy();
    expect(screen.queryByLabelText("Emergency alert")).toBeNull();
  });

  it("holding the button for 2 seconds sends one alert; letting go early sends nothing", async () => {
    let posted: Call[] = [];
    const calls = estateRoutes([], (c) => {
      if (c.url.endsWith("/me/alerts/") && c.method === "POST") {
        posted = [...posted, c];
        return json(201, myAlert());
      }
      if (c.url.endsWith("/me/alerts/al1/kind/")) return json(200, myAlert({ kind: "robbery" }));
      return undefined;
    });
    renderWithClient(<EstateHome />);
    const button = await screen.findByLabelText("Emergency alert");
    jest.useFakeTimers();
    fireEvent(button, "pressIn");
    act(() => jest.advanceTimersByTime(HOLD_MS / 2));
    fireEvent(button, "pressOut");
    act(() => jest.advanceTimersByTime(HOLD_MS));
    expect(posted).toHaveLength(0);

    fireEvent(button, "pressIn");
    act(() => jest.advanceTimersByTime(HOLD_MS));
    jest.useRealTimers();
    await waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0]!.body).toMatchObject({ estate: "es1", kind: "help", silent: false, location: null });
    expect((posted[0]!.body as { client_id: string }).client_id).toMatch(/^app-[0-9a-f]{32}$/);
    expect(Haptics.notificationAsync).toHaveBeenCalled();
    expect(await screen.findByText("Alert sent to estate security")).toBeTruthy();
    fireEvent.press(screen.getByRole("radio", { name: "Robbery / break-in" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/me/alerts/al1/kind/"))).toBe(true));
  });

  it("silent alerts don't vibrate; screen readers confirm instead of holding; location only with consent", async () => {
    await setSecure("panicLocation", "1");
    let body: Record<string, unknown> | undefined;
    estateRoutes([], (c) => {
      if (c.url.endsWith("/me/alerts/") && c.method === "POST") {
        body = c.body as Record<string, unknown>;
        return json(201, myAlert({ silent: true }));
      }
      return undefined;
    });
    const alertSpy = jest.spyOn(Alert, "alert");
    renderWithClient(<EstateHome />);
    const button = await screen.findByLabelText("Emergency alert");
    fireEvent(screen.getByRole("switch", { name: "Silent alert" }), "valueChange", true);
    fireEvent(button, "accessibilityAction", { nativeEvent: { actionName: "activate" } });
    const buttons = alertSpy.mock.calls[0]![2]!;
    act(() => buttons.find((b) => b.text === "Send alert")!.onPress!());
    await waitFor(() => expect(body).toBeDefined());
    expect(body).toMatchObject({ silent: true, location: { lat: 6.4281, lng: 3.4219, accuracy: 12 } });
    expect(Haptics.notificationAsync).not.toHaveBeenCalled();
    expect(await screen.findByText("Silent alert sent to estate security")).toBeTruthy();
  });

  it("an open alert shows its status and I'm safe cancels it", async () => {
    const calls = estateRoutes([myAlert({ status: "responding" })], (c) =>
      c.url.endsWith("/me/alerts/al1/cancel/") ? json(200, myAlert({ status: "cancelled" })) : undefined,
    );
    const alertSpy = jest.spyOn(Alert, "alert");
    renderWithClient(<EstateHome />);
    expect(await screen.findByText("Security is on the way")).toBeTruthy();
    fireEvent.press(screen.getByRole("button", { name: "I'm safe now" }));
    const buttons = alertSpy.mock.calls[0]![2]!;
    await act(async () => buttons.find((b) => b.text === "I'm safe now")!.onPress!());
    expect(calls.some((c) => c.url.endsWith("/me/alerts/al1/cancel/"))).toBe(true);
  });
});

describe("sending an alert", () => {
  it("retries network failures with the same client id, and not server refusals", async () => {
    let n = 0;
    const calls = mockFetch((c) => {
      if (!c.url.endsWith("/me/alerts/")) return undefined;
      n += 1;
      if (n < 3) throw new TypeError("Network request failed");
      return json(201, myAlert());
    });
    const alert = await sendAlert({ estate: "es1", kind: "help", silent: false, client_id: "app-same" }, { delayMs: 1 });
    expect(alert.id).toBe("al1");
    expect(calls.map((c) => (c.body as { client_id: string }).client_id)).toEqual(["app-same", "app-same", "app-same"]);

    const refused = mockFetch(() =>
      json(429, { error: { code: "panic_rate_limited", message: "Call 112 now.", details: {} } }),
    );
    await expect(sendAlert({ estate: "es1", kind: "help", silent: false, client_id: "x" }, { delayMs: 1 })).rejects.toBeInstanceOf(ApiError);
    expect(refused).toHaveLength(1);
  });
});

describe("join and gate passes", () => {
  it("joins with the code in capitals", async () => {
    const calls = mockFetch((c) => (c.url.endsWith("/me/estates/join/") ? json(201, member({ status: "pending" })) : undefined));
    renderWithClient(<JoinEstate />);
    fireEvent.changeText(screen.getByLabelText("Estate code"), "k7pm-2q");
    fireEvent.changeText(screen.getByLabelText("Your house or flat"), "A1");
    fireEvent.press(screen.getByRole("button", { name: "Ask to join" }));
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/estate"));
    expect(calls[0]!.body).toEqual({ code: "K7PM2Q", house: "A1" });
  });

  it("creates a pass and shows the code", async () => {
    (useLocalSearchParams as jest.Mock).mockReturnValue({ estate: "es1" });
    const calls = mockFetch((c) =>
      c.url.endsWith("/me/gate-passes/") && c.method === "POST"
        ? json(201, {
            id: "gp1",
            estate: "es1",
            estate_name: "Palm Grove Estate",
            visitor_name: "Tolu",
            visitor_phone: "+2348035551234",
            kind: "visitor",
            job: null,
            code: "482913",
            valid_from: "2026-10-15T09:00:00Z",
            valid_to: "2026-10-15T13:00:00Z",
            max_uses: 1,
            uses: 0,
            status: "active",
            note: "",
            created_at: "2026-10-15T09:00:00Z",
          })
        : undefined,
    );
    renderWithClient(<NewGatePass />);
    fireEvent.press(screen.getByRole("button", { name: "Create pass" }));
    expect(calls).toHaveLength(0); // needs a name
    fireEvent.changeText(screen.getByLabelText("Visitor's name"), "Tolu");
    fireEvent.changeText(screen.getByLabelText("Visitor's phone"), "08035551234");
    fireEvent.press(screen.getByRole("radio", { name: "4 hours" }));
    fireEvent.press(screen.getByRole("button", { name: "Create pass" }));
    expect(await screen.findByText("482913")).toBeTruthy();
    expect(calls[0]!.body).toMatchObject({ estate: "es1", visitor_name: "Tolu", visitor_phone: "+2348035551234", hours: 4, max_uses: 1 });
    expect(calls[0]!.headers["Idempotency-Key"]).toMatch(/^pass_/);
    expect(screen.getByText("We've texted the code to +234 803 555 1234.")).toBeTruthy();
  });
});

describe("alert push opened", () => {
  it("a guard sees the details, says it was received and acknowledges", async () => {
    (useLocalSearchParams as jest.Mock).mockReturnValue({ id: "al1", org: "org-1" });
    const desk = {
      id: "al1",
      estate_name: "Palm Grove Estate",
      kind: "robbery",
      status: "triggered",
      silent: false,
      raised_by_name: "Ngozi Eze",
      raised_by_phone: "+2348031112222",
      house: "A1",
      location: null,
      created_at: "2026-10-15T09:00:00Z",
    };
    const calls = mockFetch((c) => {
      if (c.url.endsWith("/me/alerts/al1/received/")) return new Response(null, { status: 204 });
      if (c.url.endsWith("/orgs/org-1/alerts/al1/") && c.method === "GET") return json(200, desk);
      if (c.url.endsWith("/orgs/org-1/alerts/al1/acknowledge/")) return json(200, { ...desk, status: "acknowledged" });
      return undefined;
    });
    renderWithClient(<AlertScreen />);
    expect(await screen.findByText("House A1")).toBeTruthy();
    expect(calls.some((c) => c.url.endsWith("/received/"))).toBe(true);
    fireEvent.press(screen.getByRole("button", { name: "I've seen it" }));
    expect(await screen.findByText("Security has seen your alert")).toBeTruthy();
  });

  it("a neighbour gets the safety message", async () => {
    (useLocalSearchParams as jest.Mock).mockReturnValue({ id: "al1" });
    mockFetch((c) => (c.url.endsWith("/received/") ? new Response(null, { status: 204 }) : undefined));
    renderWithClient(<AlertScreen />);
    expect(await screen.findByText(/A neighbour raised an emergency alert/)).toBeTruthy();
  });
});
