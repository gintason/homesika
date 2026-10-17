import { strings } from "../i18n";
import { API_PREFIX, API_URL } from "./config";
import { refreshAccess, session } from "./session";

/** The API's error envelope: {"error": {"code", "message", "details"}}. Branch on `code`, never `message`. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;
  /** First message per field, e.g. {"phone_number": "An account with this phone number already exists."} */
  readonly fieldErrors: Record<string, string>;
  /** Errors not tied to a field (non_field_errors, or a list-shaped validation error). */
  readonly formErrors: string[];

  constructor(status: number, code: string, message: string, details: unknown = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    const { fields, form } = flattenDetails(details);
    this.fieldErrors = fields;
    this.formErrors = form;
  }

  /** The most useful single line to show: a form-level error, else the envelope message. */
  get summary(): string {
    return this.formErrors[0] ?? this.message;
  }
}

function firstMessage(value: unknown): string | undefined {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) {
    for (const v of value) {
      const m = firstMessage(v);
      if (m) return m;
    }
    return undefined;
  }
  if (value && typeof value === "object") {
    for (const v of Object.values(value)) {
      const m = firstMessage(v);
      if (m) return m;
    }
  }
  return undefined;
}

function flattenDetails(details: unknown): { fields: Record<string, string>; form: string[] } {
  const fields: Record<string, string> = {};
  const form: string[] = [];
  if (Array.isArray(details) || typeof details === "string") {
    const m = firstMessage(details);
    if (m) form.push(m);
  } else if (details && typeof details === "object") {
    for (const [key, value] of Object.entries(details)) {
      const m = firstMessage(value);
      if (!m) continue;
      if (key === "non_field_errors" || key === "detail") form.push(m);
      else fields[key] = m;
    }
  }
  return { fields, form };
}

export type Query = Record<string, string | number | boolean | null | undefined>;

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  query?: Query;
  /** Send the access token and refresh it once on 401 (default true). */
  auth?: boolean;
  /** Idempotency-Key header for money-moving / message-sending POSTs. Reuse it when retrying. */
  idempotencyKey?: string;
  signal?: AbortSignal;
  accept?: string;
}

export function apiUrl(path: string, query?: Query): string {
  const base = /^https?:\/\//.test(path) ? path : `${API_URL}${API_PREFIX}${path}`;
  if (!query) return base;
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null || v === "" || v === false) continue;
    params.set(k, v === true ? "1" : String(v));
  }
  const qs = params.toString();
  if (!qs) return base;
  return `${base}${base.includes("?") ? "&" : "?"}${qs}`;
}

async function toApiError(res: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    /* not JSON (proxy error page etc.) */
  }
  const env = (body as { error?: { code?: string; message?: string; details?: unknown } } | null)?.error;
  if (env && typeof env === "object") {
    return new ApiError(res.status, env.code ?? "error", env.message ?? strings.errors.generic, env.details ?? {});
  }
  if (res.status === 404) return new ApiError(404, "not_found", strings.errors.notFound);
  return new ApiError(res.status, res.status >= 500 ? "server_error" : "error", strings.errors.generic);
}

/** fetch() with the API's conventions. Throws ApiError on any non-2xx response or network failure. */
export async function apiFetch(path: string, opts: RequestOptions = {}): Promise<Response> {
  const { method = "GET", body, query, auth = true, idempotencyKey, signal, accept = "application/json" } = opts;
  const url = apiUrl(path, query);

  // FormData (photo uploads) goes as multipart: the browser sets Content-Type with the boundary.
  const isForm = typeof FormData !== "undefined" && body instanceof FormData;
  const send = () => {
    const headers: Record<string, string> = { Accept: accept, "Accept-Language": "en" };
    if (body !== undefined && !isForm) headers["Content-Type"] = "application/json";
    if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey;
    const token = auth ? session.getAccess() : null;
    if (token) headers.Authorization = `Bearer ${token}`;
    return fetch(url, {
      method,
      headers,
      body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
      signal,
    });
  };

  let res: Response;
  try {
    res = await send();
    // Access token missing or expired: refresh once, then retry once. Never loops.
    if (res.status === 401 && auth && session.getRefresh()) {
      const refreshed = await refreshAccess();
      if (refreshed) res = await send();
    }
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(0, "network_error", strings.errors.network);
  }
  if (!res.ok) throw await toApiError(res);
  return res;
}

/** JSON request. Resolves to undefined for 204 No Content. */
export async function api<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const res = await apiFetch(path, opts);
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

/** Binary download (receipt PDF, CSV) with auth. Returns the blob and the server's filename if any. */
export async function apiBlob(
  path: string,
  opts: RequestOptions = {},
): Promise<{ blob: Blob; filename: string | null }> {
  const res = await apiFetch(path, { accept: "*/*", ...opts });
  const cd = res.headers.get("Content-Disposition") ?? "";
  const match = /filename="?([^";]+)"?/.exec(cd);
  return { blob: await res.blob(), filename: match?.[1] ?? null };
}

export function isApiError(e: unknown): e is ApiError {
  return e instanceof ApiError;
}

/** Friendly text for any thrown value. */
export function errorText(e: unknown): string {
  if (e instanceof ApiError) return e.summary;
  return strings.errors.generic;
}
