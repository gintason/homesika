import Constants from "expo-constants";
import { Platform } from "react-native";
import { create } from "zustand";

import { authApi, type SignedIn, type User } from "@/api";
import { CHECKOUT_LOCK_GRACE_MS } from "@/config";
import i18n, { deviceLanguage, isSupported, type LanguageCode } from "@/i18n";
import { ApiError, setSessionExpiredHandler } from "@/lib/api";
import {
  clearBiometricPin,
  deleteSecure,
  device,
  getSecure,
  readBiometricPin,
  setSecure,
  storeBiometricPin,
  tokens,
} from "@/lib/secure";
import { biometricsAvailable } from "@/lib/security";

/**
 * booting   -> reading secure storage
 * signedOut -> this phone isn't linked to an account: welcome / sign up / sign in
 * locked    -> phone is linked: the PIN screen (every launch, and after time in the background)
 * ready     -> signed in and unlocked
 */
export type SessionStatus = "booting" | "signedOut" | "locked" | "ready";

export type Profile = { firstName: string; lastName: string; phone: string };

type SessionState = {
  status: SessionStatus;
  profile: Profile | null;
  biometricEnabled: boolean;
  language: LanguageCode;
  /** Epoch ms until which backgrounding won't lock the app (payer is in the checkout browser). */
  lockSuspendedUntil: number;
  hydrate: () => Promise<void>;
  /** After OTP / PIN setup: remember this phone and sign in. */
  completeSignIn: (result: SignedIn) => Promise<void>;
  /** PIN screen. Throws ApiError (a wrong PIN carries details.attempts_left). */
  unlockWithPin: (pin: string) => Promise<void>;
  unlockWithBiometrics: () => Promise<boolean>;
  lock: () => void;
  suspendLockForCheckout: () => void;
  resumeLock: () => void;
  logout: () => Promise<void>;
  /** "Not you?" on the PIN screen: unlink this phone without a server call. */
  switchAccount: () => Promise<void>;
  enableBiometrics: (pin: string) => Promise<boolean>;
  disableBiometrics: () => Promise<void>;
  setLanguage: (code: LanguageCode) => Promise<void>;
  updateProfile: (user: User) => Promise<void>;
};

export function deviceName(): string {
  return (Constants.deviceName || (Platform.OS === "ios" ? "iPhone" : "Android phone")).slice(0, 100);
}

function profileOf(user: User): Profile {
  return { firstName: user.first_name, lastName: user.last_name, phone: user.phone_number };
}

export const useSession = create<SessionState>((set, get) => ({
  status: "booting",
  profile: null,
  biometricEnabled: false,
  language: "en",
  lockSuspendedUntil: 0,

  hydrate: async () => {
    const [saved, biometric, secret, profile] = await Promise.all([
      getSecure("language"),
      getSecure("biometric"),
      device.secret(),
      getSecure("profile"),
    ]);
    const language = isSupported(saved) ? saved : deviceLanguage();
    await i18n.changeLanguage(language);
    const biometricEnabled = biometric === "1" && (await biometricsAvailable());

    // A linked phone ALWAYS starts at the PIN screen; old tokens are never reused across launches.
    await tokens.clear();
    let parsed: Profile | null = null;
    try {
      parsed = profile ? (JSON.parse(profile) as Profile) : null;
    } catch {
      parsed = null;
    }
    set({ status: secret ? "locked" : "signedOut", language, biometricEnabled, profile: parsed });
  },

  completeSignIn: async (result) => {
    const profile = profileOf(result.user);
    await Promise.all([
      tokens.set(result.tokens.access, result.tokens.refresh),
      setSecure("deviceSecret", result.device_secret),
      setSecure("profile", JSON.stringify(profile)),
    ]);
    set({ status: "ready", profile });
  },

  unlockWithPin: async (pin) => {
    const [id, secret] = await Promise.all([device.id(), device.secret()]);
    if (!secret) {
      set({ status: "signedOut" });
      throw new ApiError(401, "device_not_recognised", i18n.t("errors.codes.device_not_recognised"));
    }
    try {
      const { user, tokens: pair } = await authApi.pinLogin(id, secret, pin);
      const profile = profileOf(user);
      await Promise.all([tokens.set(pair.access, pair.refresh), setSecure("profile", JSON.stringify(profile))]);
      set({ status: "ready", profile });
    } catch (e) {
      if (e instanceof ApiError && e.code === "device_not_recognised") {
        await device.forget(); // signed out elsewhere (e.g. PIN reset): sign in again with a code
        set({ status: "signedOut", profile: null, biometricEnabled: false });
      }
      throw e;
    }
  },

  unlockWithBiometrics: async () => {
    if (!get().biometricEnabled) return false;
    const pin = await readBiometricPin(i18n.t("lock.prompt"));
    if (!pin) return false;
    try {
      await get().unlockWithPin(pin);
      return true;
    } catch (e) {
      // PIN changed on another device: the stored copy is stale, fall back to typing it.
      if (e instanceof ApiError && e.code === "invalid_login_pin") await get().disableBiometrics();
      return false;
    }
  },

  lock: () => {
    if (get().status === "ready") {
      tokens.clear().catch(() => {});
      set({ status: "locked" });
    }
  },

  suspendLockForCheckout: () => set({ lockSuspendedUntil: Date.now() + CHECKOUT_LOCK_GRACE_MS }),
  resumeLock: () => set({ lockSuspendedUntil: 0 }),

  logout: async () => {
    const [{ refresh }, id] = await Promise.all([tokens.get(), device.id()]);
    if (refresh) authApi.logout(refresh, id).catch(() => {}); // best effort: the server forgets this phone
    await Promise.all([tokens.clear(), device.forget()]);
    set({ status: "signedOut", profile: null, biometricEnabled: false, lockSuspendedUntil: 0 });
  },

  switchAccount: async () => {
    await Promise.all([tokens.clear(), device.forget()]);
    set({ status: "signedOut", profile: null, biometricEnabled: false, lockSuspendedUntil: 0 });
  },

  enableBiometrics: async (pin) => {
    if (!(await biometricsAvailable())) return false;
    if (!(await storeBiometricPin(pin, i18n.t("lock.prompt")))) return false;
    await setSecure("biometric", "1");
    set({ biometricEnabled: true });
    return true;
  },

  disableBiometrics: async () => {
    await Promise.all([clearBiometricPin(), deleteSecure("biometric")]);
    set({ biometricEnabled: false });
  },

  setLanguage: async (code) => {
    await i18n.changeLanguage(code);
    set({ language: code });
    await setSecure("language", code).catch(() => {});
    if (get().status === "ready") authApi.updateMe({ preferred_language: code }).catch(() => {});
  },

  updateProfile: async (user) => {
    const profile = profileOf(user);
    set({ profile });
    await setSecure("profile", JSON.stringify(profile)).catch(() => {});
  },
}));

// Refresh token rejected mid-session: back to the PIN screen (or sign-in if the phone isn't linked).
setSessionExpiredHandler(() => {
  tokens.clear().finally(async () => {
    const linked = Boolean(await device.secret());
    useSession.setState({ status: linked ? "locked" : "signedOut" });
  });
});
