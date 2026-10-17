import * as Location from "expo-location";

import { alertsApi, type MyAlert, type TriggerInput } from "@/api";

import { ApiError } from "./api";
import { randomHex } from "./idempotency";

/** How long the panic button must be held. */
export const HOLD_MS = 2000;

export const newClientId = () => `app-${randomHex()}`;

/**
 * Where the phone is, if the person agreed to share it and it can be found quickly. Never blocks an
 * alert for long: gives up after `timeoutMs`.
 */
export async function currentLocation(timeoutMs = 4000): Promise<TriggerInput["location"]> {
  try {
    const perm = await Location.requestForegroundPermissionsAsync();
    if (perm.status !== "granted") return null;
    const pos = await Promise.race([
      Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced }),
      new Promise<null>((resolve) => setTimeout(() => resolve(null), timeoutMs)),
    ]);
    if (!pos) return null;
    return { lat: pos.coords.latitude, lng: pos.coords.longitude, accuracy: pos.coords.accuracy ?? null };
  } catch {
    return null;
  }
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/**
 * Send an alert, retrying network failures with the SAME client_id (the server returns the same alert,
 * so a retry never raises two). Errors the server gave (rate limit, not a resident) are not retried.
 */
export async function sendAlert(input: TriggerInput, { attempts = 4, delayMs = 1000 } = {}): Promise<MyAlert> {
  let last: unknown;
  for (let i = 0; i < attempts; i++) {
    try {
      return await alertsApi.trigger(input);
    } catch (err) {
      last = err;
      if (!(err instanceof ApiError) || !(err.isNetwork || err.status >= 500)) throw err;
      if (i < attempts - 1) await sleep(delayMs * 2 ** i);
    }
  }
  throw last;
}

export const isOpen = (a: Pick<MyAlert, "status">) => ["triggered", "acknowledged", "responding"].includes(a.status);
