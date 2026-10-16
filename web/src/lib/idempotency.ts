import { useCallback, useRef } from "react";

/** A fresh Idempotency-Key (16-64 chars of [A-Za-z0-9_-:.]). */
export function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

/**
 * One key per submission. Retrying the SAME payload (double tap, flaky network, "Try again") reuses the
 * key so the server replays the first result instead of recording money twice. A changed payload gets a
 * new key, because the server refuses a reused key with a different body (idempotency_key_reused).
 * Call reset() after a success so the next, separate submission is new.
 */
export function useIdempotencyKey() {
  const ref = useRef<{ body: string; key: string } | null>(null);
  const keyFor = useCallback((payload: unknown): string => {
    const body = JSON.stringify(payload);
    if (!ref.current || ref.current.body !== body) ref.current = { body, key: newIdempotencyKey() };
    return ref.current.key;
  }, []);
  const reset = useCallback(() => {
    ref.current = null;
  }, []);
  return { keyFor, reset };
}
