import * as SecureStore from "expo-secure-store";

import { randomHex } from "./idempotency";

/**
 * Keychain (iOS) / Keystore-backed (Android) storage for secrets.
 * WHEN_UNLOCKED_THIS_DEVICE_ONLY: never synced to iCloud, never restored to another device.
 */
const OPTIONS: SecureStore.SecureStoreOptions = {
  keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
};

const KEYS = {
  access: "homesika.access",
  refresh: "homesika.refresh",
  biometric: "homesika.biometric",
  biometricAsked: "homesika.biometricAsked",
  language: "homesika.language",
  /** Random id for this install; survives sign-out so the server can recognise the phone. */
  deviceId: "homesika.deviceId",
  /** Issued by the server once this phone is verified by OTP: PIN-only login needs it. */
  deviceSecret: "homesika.deviceSecret",
  /** {firstName, phone} for the "Welcome back" PIN screen. */
  profile: "homesika.profile",
} as const;

export type SecureKey = keyof typeof KEYS;

export async function getSecure(key: SecureKey): Promise<string | null> {
  return SecureStore.getItemAsync(KEYS[key], OPTIONS);
}

export async function setSecure(key: SecureKey, value: string): Promise<void> {
  await SecureStore.setItemAsync(KEYS[key], value, OPTIONS);
}

export async function deleteSecure(key: SecureKey): Promise<void> {
  await SecureStore.deleteItemAsync(KEYS[key], OPTIONS);
}

export const tokens = {
  async get() {
    const [access, refresh] = await Promise.all([getSecure("access"), getSecure("refresh")]);
    return { access, refresh };
  },
  async set(access: string, refresh: string) {
    await Promise.all([setSecure("access", access), setSecure("refresh", refresh)]);
  },
  async clear() {
    await Promise.all([deleteSecure("access"), deleteSecure("refresh")]);
  },
};

/**
 * The login PIN, kept only for Face ID / fingerprint unlock: the OS releases it after a successful
 * biometric check (and invalidates it if the enrolled faces/fingers change).
 */
const BIO_KEY = "homesika.bioPin";

export async function storeBiometricPin(pin: string, prompt: string): Promise<boolean> {
  try {
    await SecureStore.setItemAsync(BIO_KEY, pin, { ...OPTIONS, requireAuthentication: true, authenticationPrompt: prompt });
    return true;
  } catch {
    return false;
  }
}

export async function readBiometricPin(prompt: string): Promise<string | null> {
  try {
    return await SecureStore.getItemAsync(BIO_KEY, { ...OPTIONS, requireAuthentication: true, authenticationPrompt: prompt });
  } catch {
    return null; // cancelled, failed, or biometrics changed
  }
}

export async function clearBiometricPin(): Promise<void> {
  await SecureStore.deleteItemAsync(BIO_KEY, OPTIONS).catch(() => {});
}

export const device = {
  /** Backend accepts ^[A-Za-z0-9_-]{16,64}$. */
  async id(): Promise<string> {
    const existing = await getSecure("deviceId");
    if (existing) return existing;
    const fresh = `dev_${randomHex()}`;
    await setSecure("deviceId", fresh);
    return fresh;
  },
  secret: () => getSecure("deviceSecret"),
  async forget() {
    await Promise.all([
      deleteSecure("deviceSecret"),
      deleteSecure("profile"),
      clearBiometricPin(),
      deleteSecure("biometric"),
    ]);
  },
};
