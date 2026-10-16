import { storage } from "./storage";

/*
 * The browser acts as a "device" for the API's device binding (PIN-only login on a trusted device).
 *
 * Trade-off (deliberate): the device secret and the refresh token are kept in localStorage so a
 * landlord stays signed in across reloads and can come back with just their PIN. localStorage is
 * readable by any script on this origin, so an XSS bug would expose them. We limit the blast
 * radius: the access token lives only in memory, the refresh token is short-lived and rotated on
 * every use (blacklisted after rotation), the device secret alone is useless without the 6-digit
 * PIN, and "Sign out" revokes the device server-side. Moving to httpOnly cookies needs backend work.
 */

const DEVICE_ID = "hs.device_id";
const DEVICE_SECRET = "hs.device_secret";
const LAST_PHONE = "hs.last_phone";

function randomId(): string {
  const bytes = new Uint8Array(18);
  crypto.getRandomValues(bytes);
  const b64 = btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
  return `web-${b64}`; // 28 chars of [A-Za-z0-9_-], matches the API's device_id rule (16-64)
}

export function getDeviceId(): string {
  let id = storage.get(DEVICE_ID);
  if (!id || !/^[A-Za-z0-9_-]{16,64}$/.test(id)) {
    id = randomId();
    storage.set(DEVICE_ID, id);
  }
  return id;
}

export function getDeviceName(): string {
  const ua = typeof navigator !== "undefined" ? navigator.userAgent : "";
  const browser = /Edg\//.test(ua)
    ? "Edge"
    : /OPR\//.test(ua)
      ? "Opera"
      : /Chrome\//.test(ua)
        ? "Chrome"
        : /Firefox\//.test(ua)
          ? "Firefox"
          : /Safari\//.test(ua)
            ? "Safari"
            : "Browser";
  const os = /Android/.test(ua)
    ? "Android"
    : /iPhone|iPad/.test(ua)
      ? "iOS"
      : /Windows/.test(ua)
        ? "Windows"
        : /Mac OS/.test(ua)
          ? "macOS"
          : /Linux/.test(ua)
            ? "Linux"
            : "";
  return `Web: ${browser}${os ? ` on ${os}` : ""}`.slice(0, 100);
}

export const deviceSecret = {
  get: () => storage.get(DEVICE_SECRET),
  set: (s: string) => storage.set(DEVICE_SECRET, s),
  clear: () => storage.remove(DEVICE_SECRET),
};

export const lastPhone = {
  get: () => storage.get(LAST_PHONE),
  set: (p: string) => storage.set(LAST_PHONE, p),
  clear: () => storage.remove(LAST_PHONE),
};
