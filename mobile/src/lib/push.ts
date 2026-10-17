import Constants from "expo-constants";
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import { Platform } from "react-native";

import { pushApi } from "@/api";

import { deleteSecure, getSecure, setSecure } from "./secure";

/**
 * Push notifications (Expo push service: backend/apps/notifications/push.py).
 * Two Android channels: "alerts" (panic alerts: loudest, shows on the lock screen) and "default".
 */
export function configureNotifications() {
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowBanner: true,
      shouldShowList: true,
      shouldPlaySound: true,
      shouldSetBadge: false,
    }),
  });
}

async function setupChannels(names: { alerts: string; updates: string }) {
  if (Platform.OS !== "android") return;
  await Notifications.setNotificationChannelAsync("alerts", {
    name: names.alerts,
    importance: Notifications.AndroidImportance.MAX,
    sound: "default",
    vibrationPattern: [0, 500, 250, 500, 250, 500],
    lockscreenVisibility: Notifications.AndroidNotificationVisibility.PUBLIC,
  });
  await Notifications.setNotificationChannelAsync("default", {
    name: names.updates,
    importance: Notifications.AndroidImportance.DEFAULT,
  });
}

/** EAS project id from app.json (extra.eas.projectId). TODO(verify): set it after `eas init`. */
export function easProjectId(): string | undefined {
  const extra = Constants.expoConfig?.extra as { eas?: { projectId?: string } } | undefined;
  return extra?.eas?.projectId ?? Constants.easConfig?.projectId ?? undefined;
}

export type PushResult = "registered" | "denied" | "unavailable";

/** Ask once after sign-in; register this phone's token with the server. Never throws. */
export async function registerForPush(names: { alerts: string; updates: string }): Promise<PushResult> {
  try {
    if (!Device.isDevice) return "unavailable"; // simulators can't receive pushes
    await setupChannels(names);
    let { status } = await Notifications.getPermissionsAsync();
    if (status !== "granted") status = (await Notifications.requestPermissionsAsync()).status;
    if (status !== "granted") return "denied";
    const projectId = easProjectId();
    if (!projectId) return "unavailable";
    const { data } = await Notifications.getExpoPushTokenAsync({ projectId });
    await pushApi.register(data, Platform.OS === "ios" ? "ios" : "android");
    await setSecure("pushToken", data);
    return "registered";
  } catch {
    return "unavailable"; // SMS still reaches the person; we'll try again next launch
  }
}

/** On sign-out: stop pushes to this phone for this account (best effort). */
export async function unregisterPush(): Promise<void> {
  const token = await getSecure("pushToken");
  if (!token) return;
  await pushApi.unregister(token).catch(() => {});
  await deleteSecure("pushToken");
}

export type PushData = { type?: string; alert?: string; estate?: string; org?: string; audience?: string };

/** Where a tapped notification should take the person. */
export function routeFor(data: PushData): { pathname: string; params?: Record<string, string> } | null {
  if (data.type === "panic" && data.alert) {
    return { pathname: "/alert/[id]", params: { id: data.alert, ...(data.org ? { org: data.org } : {}) } };
  }
  if (data.type === "panic_status" || data.type === "announcement" || data.type === "gate") return { pathname: "/estate" };
  return null;
}
