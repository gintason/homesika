import * as Crypto from "expo-crypto";

/** 32 random hex characters (expo-crypto when available, Math.random as a last resort). */
export function randomHex(): string {
  try {
    const uuid = Crypto.randomUUID();
    if (uuid) return uuid.replace(/-/g, "");
  } catch {
    // native module missing (e.g. some test or web setups)
  }
  let out = "";
  for (let i = 0; i < 32; i++) out += Math.floor(Math.random() * 16).toString(16);
  return out;
}

/**
 * A fresh Idempotency-Key for one money action. The backend accepts 16–64 chars of
 * [A-Za-z0-9_-:.]. Reuse the same key when retrying the SAME submit after a network error.
 */
export function newIdempotencyKey(prefix = "pay"): string {
  return `${prefix}_${randomHex()}`;
}
