import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { api } from "./api";
import { deviceSecret, getDeviceId, lastPhone } from "./device";
import { refreshAccess, session } from "./session";
import type { SignedIn, User } from "./types";

export type AuthStatus = "loading" | "signedOut" | "signedIn" | "error";

interface AuthContextValue {
  status: AuthStatus;
  user: User | null;
  /** Store tokens (+ device secret) from pin-login, otp/verify or pin/setup and mark the user signed in. */
  completeSignIn: (resp: SignedIn) => void;
  signOut: () => Promise<void>;
  /** Re-run the start-up check after a network failure. */
  retry: () => void;
  /** True when this browser can sign in with just the PIN (it holds a device secret). */
  isTrustedDevice: () => boolean;
}

/** Keep tokens + device secret without changing the app's signed-in state (used mid sign-up). */
export function storeCredentials(resp: SignedIn): void {
  session.setTokens(resp.tokens);
  if (resp.device_secret) deviceSecret.set(resp.device_secret);
  lastPhone.set(resp.user.phone_number);
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<AuthStatus>(() => (session.getRefresh() ? "loading" : "signedOut"));
  const [user, setUser] = useState<User | null>(null);
  const [attempt, setAttempt] = useState(0);

  // Start-up: a stored refresh token means we can restore the session without asking for the PIN.
  useEffect(() => {
    if (!session.getRefresh()) return;
    let cancelled = false;
    (async () => {
      const ok = session.getAccess() ? true : await refreshAccess();
      if (cancelled) return;
      if (!ok) {
        // Token still stored => the refresh failed for a network reason, not because it was rejected.
        setStatus(session.getRefresh() ? "error" : "signedOut");
        return;
      }
      try {
        const me = await api<User>("/me/");
        if (cancelled) return;
        setUser(me);
        setStatus("signedIn");
      } catch {
        if (!cancelled) setStatus(session.getRefresh() ? "error" : "signedOut");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  useEffect(
    () =>
      session.onExpired(() => {
        setUser(null);
        setStatus("signedOut");
        queryClient.clear();
      }),
    [queryClient],
  );

  const completeSignIn = useCallback((resp: SignedIn) => {
    storeCredentials(resp);
    setUser(resp.user);
    setStatus("signedIn");
  }, []);

  const signOut = useCallback(async () => {
    const refresh = session.getRefresh();
    try {
      if (refresh) {
        await api("/auth/logout/", { method: "POST", body: { refresh, device_id: getDeviceId() } });
      }
    } catch {
      /* signing out locally still happens */
    } finally {
      session.clear();
      deviceSecret.clear(); // the server revoked this device, so the secret is useless now
      queryClient.clear();
      setUser(null);
      setStatus("signedOut");
    }
  }, [queryClient]);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      completeSignIn,
      signOut,
      retry: () => {
        setStatus("loading");
        setAttempt((n) => n + 1);
      },
      isTrustedDevice: () => Boolean(deviceSecret.get() && lastPhone.get()),
    }),
    [status, user, completeSignIn, signOut],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
