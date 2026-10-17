/**
 * Backend base URL from EXPO_PUBLIC_API_URL (see mobile/.env.example).
 * iOS Simulator: http://localhost:8001 · Android emulator: http://10.0.2.2:8001.
 */
export const API_URL = (process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8001").replace(/\/$/, "");

/** Optional links shown on sign-up. Leave unset until the pages are published. */
export const TERMS_URL = process.env.EXPO_PUBLIC_TERMS_URL || null;
export const PRIVACY_URL = process.env.EXPO_PUBLIC_PRIVACY_URL || null;

/** Lock the app (PIN screen) after this long in the background. */
export const LOCK_AFTER_BACKGROUND_MS = 2 * 60 * 1000;

/** While the payment checkout is open, don't lock for up to this long (the payer is in the browser). */
export const CHECKOUT_LOCK_GRACE_MS = 20 * 60 * 1000;

/** The Homesika web dashboard (security staff open the live desk there). Unset: the button is hidden. */
export const WEB_URL = (process.env.EXPO_PUBLIC_WEB_URL || "").replace(/\/$/, "") || null;
