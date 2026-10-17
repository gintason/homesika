import { vi } from "vitest";

export interface Recorded {
  method: string;
  path: string;
  search: URLSearchParams;
  headers: Record<string, string>;
  body: unknown;
}

type Reply = { status?: number; body?: unknown; headers?: Record<string, string>; raw?: string | Blob } | Error;
type Handler = Reply | ((req: Recorded, nth: number) => Reply | Promise<Reply>);

/**
 * Replace global fetch. Keys are "METHOD /api/v1/path/" (query string ignored). A handler may be a
 * static reply, an Error (network failure) or a function of the request. Unmatched requests fail the test.
 */
export function mockFetch(routes: Record<string, Handler>) {
  const calls: Recorded[] = [];
  const counts = new Map<string, number>();
  const fn = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = new URL(typeof input === "string" ? input : input.toString(), "http://test.local");
    const method = (init.method ?? "GET").toUpperCase();
    const headers = Object.fromEntries(Object.entries((init.headers ?? {}) as Record<string, string>));
    const req: Recorded = {
      method,
      path: url.pathname,
      search: url.searchParams,
      headers,
      body:
        typeof init.body === "string" ? JSON.parse(init.body) : init.body instanceof FormData ? init.body : undefined,
    };
    calls.push(req);
    const key = `${method} ${url.pathname}`;
    const handler = routes[key];
    if (handler === undefined) throw new Error(`Unexpected request: ${key}`);
    const nth = (counts.get(key) ?? 0) + 1;
    counts.set(key, nth);
    const reply = typeof handler === "function" ? await handler(req, nth) : handler;
    if (reply instanceof Error) throw reply;
    const status = reply.status ?? 200;
    if (reply.raw !== undefined) return new Response(reply.raw, { status, headers: reply.headers });
    const noBody = status === 204 || reply.body === undefined;
    return new Response(noBody ? null : JSON.stringify(reply.body), {
      status,
      headers: { "Content-Type": "application/json", ...reply.headers },
    });
  });
  vi.stubGlobal("fetch", fn);
  return { fn, calls, find: (method: string, path: string) => calls.filter((c) => c.method === method && c.path === path) };
}

export function envelope(status: number, code: string, message: string, details: unknown = {}): Reply {
  return { status, body: { error: { code, message, details } } };
}
