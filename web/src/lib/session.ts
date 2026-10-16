import { API_PREFIX, API_URL } from "./config";
import { storage } from "./storage";

/**
 * Tokens. The access token lives only in memory (lost on reload, re-minted from the refresh token).
 * The refresh token is in localStorage so a reload doesn't sign the user out: see the trade-off note
 * in device.ts. The API rotates refresh tokens on every use, so we always store the newest one.
 */
const REFRESH_KEY = "hs.refresh";

let accessToken: string | null = null;
let refreshing: Promise<boolean> | null = null;
const expiredListeners = new Set<() => void>();

export interface Tokens {
  access: string;
  refresh?: string;
}

export const session = {
  getAccess: () => accessToken,
  getRefresh: () => storage.get(REFRESH_KEY),
  setTokens(tokens: Tokens) {
    accessToken = tokens.access;
    if (tokens.refresh) storage.set(REFRESH_KEY, tokens.refresh);
  },
  clear() {
    accessToken = null;
    storage.remove(REFRESH_KEY);
  },
  /** Called when the session can't be refreshed any more (refresh token expired or revoked). */
  onExpired(listener: () => void): () => void {
    expiredListeners.add(listener);
    return () => expiredListeners.delete(listener);
  },
};

/** Swap the refresh token for a new access token. Concurrent callers share one request. */
export function refreshAccess(): Promise<boolean> {
  if (refreshing) return refreshing;
  const refresh = session.getRefresh();
  if (!refresh) return Promise.resolve(false);
  refreshing = (async () => {
    try {
      const res = await fetch(`${API_URL}${API_PREFIX}/auth/refresh/`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ refresh }),
      });
      if (!res.ok) {
        // Only a definite rejection ends the session; a network blip or 5xx keeps the token for later.
        if (res.status === 401 || res.status === 400) {
          session.clear();
          expiredListeners.forEach((l) => l());
        }
        return false;
      }
      const data = (await res.json()) as Tokens;
      session.setTokens(data);
      return true;
    } catch {
      return false;
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}
