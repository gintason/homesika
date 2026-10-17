import * as Notifications from "expo-notifications";

import { registerForPush, routeFor, unregisterPush } from "@/lib/push";
import { getSecure, tokens } from "@/lib/secure";
import { json, mockFetch } from "@/testing/utils";

jest.mock("expo-constants", () => ({ __esModule: true, default: { expoConfig: { extra: { eas: { projectId: "proj-1" } } } } }));

beforeEach(async () => {
  jest.clearAllMocks();
  await tokens.set("access-1", "refresh-1");
});

describe("push", () => {
  it("registers this phone's token after permission, and removes it on sign-out", async () => {
    const calls = mockFetch((c) => (c.url.endsWith("/me/push-devices/") ? new Response(null, { status: 204 }) : json(404, {})));
    expect(await registerForPush({ alerts: "Emergency alert", updates: "News" })).toBe("registered");
    expect(Notifications.getExpoPushTokenAsync).toHaveBeenCalledWith({ projectId: "proj-1" });
    expect(calls[0]).toMatchObject({ method: "POST", body: { token: "ExponentPushToken[test-device-0001]" } });
    expect(await getSecure("pushToken")).toBe("ExponentPushToken[test-device-0001]");
    await unregisterPush();
    expect(calls[1]).toMatchObject({ method: "DELETE", body: { token: "ExponentPushToken[test-device-0001]" } });
    expect(await getSecure("pushToken")).toBeNull();
  });

  it("doesn't register without permission", async () => {
    (Notifications.getPermissionsAsync as jest.Mock).mockResolvedValueOnce({ status: "denied" });
    (Notifications.requestPermissionsAsync as jest.Mock).mockResolvedValueOnce({ status: "denied" });
    const calls = mockFetch(() => undefined);
    expect(await registerForPush({ alerts: "a", updates: "b" })).toBe("denied");
    expect(calls).toHaveLength(0);
  });

  it("routes a tapped alert to the alert screen (with the org for staff)", () => {
    expect(routeFor({ type: "panic", alert: "al1", org: "org-1" })).toEqual({ pathname: "/alert/[id]", params: { id: "al1", org: "org-1" } });
    expect(routeFor({ type: "panic", alert: "al1" })).toEqual({ pathname: "/alert/[id]", params: { id: "al1" } });
    expect(routeFor({ type: "announcement" })).toEqual({ pathname: "/estate" });
    expect(routeFor({ type: "other" })).toBeNull();
  });
});
