import { useCallback, useEffect, useRef, useState } from "react";
import { AppState } from "react-native";

import { tenantApi, type PayLinkStatus } from "@/api";

export type PayPhase = "checking" | "paid" | "processing" | "failed";

/** Waits between status checks: quick at first, then backing off (≈ 20 s in total). */
export const POLL_DELAYS_MS = [0, 2000, 3000, 5000, 8000];

/**
 * Poll GET /pay/{reference}/status/ (public; the backend re-verifies with the gateway while pending)
 * a few times with backoff. Re-checks when the app comes back to the foreground (Android returns
 * from the checkout tab that way) and on demand ("Check again").
 */
export function usePayStatus(reference: string) {
  const [phase, setPhase] = useState<PayPhase>("checking");
  const [linkStatus, setLinkStatus] = useState<PayLinkStatus | null>(null);
  const [receiptNumber, setReceiptNumber] = useState<string | null>(null);
  const run = useRef(0);
  const final = useRef(false);

  const poll = useCallback(async () => {
    const id = ++run.current;
    for (const delay of POLL_DELAYS_MS) {
      if (delay) await new Promise((r) => setTimeout(r, delay));
      if (id !== run.current) return; // superseded by a newer poll or unmounted
      try {
        const s = await tenantApi.payStatus(reference);
        if (id !== run.current) return;
        setLinkStatus(s.status);
        if (s.status === "paid") {
          setReceiptNumber(s.receipt_number);
          final.current = true;
          setPhase("paid");
          return;
        }
        if (s.status === "expired" || s.status === "cancelled") {
          final.current = true;
          setPhase("failed");
          return;
        }
      } catch {
        // network blip: keep trying on the next tick
      }
    }
    if (id === run.current) setPhase("processing");
  }, [reference]);

  /** "Check again" / back from the browser: show the spinner, then poll. */
  const checkAgain = useCallback(() => {
    setPhase("checking");
    return poll();
  }, [poll]);

  useEffect(() => {
    const runs = run;
    const first = setTimeout(poll, 0); // start from a callback, not the effect body
    const sub = AppState.addEventListener("change", (state) => {
      if (state === "active" && !final.current) checkAgain();
    });
    return () => {
      clearTimeout(first);
      runs.current++; // stop any poll in flight
      sub.remove();
    };
  }, [poll, checkAgain]);

  return { phase, linkStatus, receiptNumber, checkAgain };
}
