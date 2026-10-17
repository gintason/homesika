import { API_URL } from "@/config";
import i18n from "@/i18n";

import { tokens } from "./secure";

/** The backend's error envelope: {"error": {"code", "message", "details"}} (apps/core/exceptions.py). */
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** First field-level validation message, if any (for showing under an input). */
  fieldMessage(field: string): string | undefined {
    const value = this.details?.[field];
    if (Array.isArray(value)) return value.length ? String(value[0]) : undefined;
    if (typeof value === "string") return value;
    return undefined;
  }

  /** Remaining PIN attempts (sent with invalid_login_pin). */
  get attemptsLeft(): number | undefined {
    const left = this.details?.attempts_left;
    return typeof left === "number" ? left : undefined;
  }

  get isNetwork(): boolean {
    return this.code === "network_error";
  }
}

export type ApiOptions = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  /** Sent as Idempotency-Key (POST /me/pay/). Reuse the same key when retrying the same submit. */
  idempotencyKey?: string;
  auth?: boolean;
  signal?: AbortSignal;
};

let onSessionExpired: () => void = () => {};
/** Called when the refresh token is rejected: the user must unlock / sign in again. */
export function setSessionExpiredHandler(fn: () => void) {
  onSessionExpired = fn;
}

// Single-flight refresh: concurrent 401s share one refresh call (the backend rotates and
// blacklists refresh tokens, so two parallel refreshes would sign the user out).
let refreshing: Promise<string | null> | null = null;

export async function refreshAccessToken(): Promise<string | null> {
  if (!refreshing) {
    refreshing = (async () => {
      const { refresh } = await tokens.get();
      if (!refresh) return null;
      try {
        const res = await fetch(`${API_URL}/api/v1/auth/refresh/`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({ refresh }),
        });
        if (!res.ok) return null;
        const data = (await res.json()) as { access: string; refresh?: string };
        await tokens.set(data.access, data.refresh ?? refresh);
        return data.access;
      } catch {
        return null;
      }
    })().finally(() => {
      refreshing = null;
    });
  }
  return refreshing;
}

function jwtExpiresAt(token: string): number | null {
  try {
    const part = token.split(".")[1];
    if (!part) return null;
    const json = atob(part.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(part.length / 4) * 4, "="));
    const exp = (JSON.parse(json) as { exp?: number }).exp;
    return typeof exp === "number" ? exp * 1000 : null;
  } catch {
    return null;
  }
}

/** An access token good for at least 30 more seconds (for requests made outside `api`, e.g. downloads). */
export async function freshAccessToken(): Promise<string | null> {
  const { access } = await tokens.get();
  const exp = access ? jwtExpiresAt(access) : null;
  if (access && (exp === null || exp - Date.now() > 30_000)) return access;
  return refreshAccessToken();
}

export function absoluteUrl(path: string): string {
  return /^https?:\/\//.test(path) ? path : `${API_URL}${path}`;
}

async function toError(res: Response): Promise<ApiError> {
  let body: { error?: { code?: string; message?: string; details?: Record<string, unknown> } } = {};
  try {
    body = await res.json();
  } catch {
    // non-JSON (proxy error page etc.)
  }
  const err = body?.error ?? {};
  const details = err.details && typeof err.details === "object" && !Array.isArray(err.details) ? err.details : {};
  return new ApiError(
    res.status,
    err.code ?? (res.status >= 500 ? "server_error" : "error"),
    err.message ?? i18n.t("errors.generic"),
    details,
  );
}

export async function api<T>(path: string, opts: ApiOptions = {}): Promise<T> {
  const { method = "GET", body, idempotencyKey, auth = true, signal } = opts;

  const send = (access: string | null) => {
    const headers: Record<string, string> = {
      Accept: "application/json",
      "Accept-Language": i18n.language || "en",
    };
    // FormData (photo uploads) goes as multipart: fetch sets Content-Type with the boundary.
    const isForm = typeof FormData !== "undefined" && body instanceof FormData;
    if (body !== undefined && !isForm) headers["Content-Type"] = "application/json";
    if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey;
    if (auth && access) headers.Authorization = `Bearer ${access}`;
    return fetch(absoluteUrl(path), {
      method,
      headers,
      body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
      signal,
    });
  };

  let res: Response;
  try {
    res = await send(auth ? (await tokens.get()).access : null);
    if (res.status === 401 && auth) {
      // Refresh once, retry once. A second 401 is returned as an error (no loop).
      const fresh = await refreshAccessToken();
      if (!fresh) {
        onSessionExpired();
        throw await toError(res);
      }
      res = await send(fresh);
    }
  } catch (e) {
    if (e instanceof ApiError) throw e;
    if ((e as Error)?.name === "AbortError") throw e;
    throw new ApiError(0, "network_error", i18n.t("errors.network"));
  }

  if (!res.ok) throw await toError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Codes we have our own (translated) copy for; anything else shows the server's message. */
const KNOWN_CODES = [
  "network_error",
  "server_error",
  "throttled",
  "invalid_login_pin",
  "login_pin_locked",
  "device_not_recognised",
  "otp_invalid",
  "otp_attempts_exceeded",
  "otp_resend_limited",
  "otp_delivery_failed",
  "setup_expired",
  "request_in_progress",
  "slot_unavailable",
  "listing_unavailable",
] as const;

/** A message to show the user for any thrown value, in their language where we can. */
export function errorText(e: unknown): string {
  if (!(e instanceof ApiError)) return i18n.t("errors.generic");
  if ((KNOWN_CODES as readonly string[]).includes(e.code)) {
    const base = i18n.t(`errors.codes.${e.code as (typeof KNOWN_CODES)[number]}`);
    return e.attemptsLeft !== undefined ? `${base} ${i18n.t("errors.attemptsLeft", { count: e.attemptsLeft })}` : base;
  }
  if (e.code === "validation_error") {
    const first = Object.keys(e.details)[0];
    const msg = first ? e.fieldMessage(first) : undefined;
    if (msg) return msg;
  }
  return e.message || i18n.t("errors.generic");
}
