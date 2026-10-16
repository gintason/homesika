import { router } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import { useRef, useState } from "react";

import { tenantApi } from "@/api";
import { ApiError, errorText } from "@/lib/api";
import { newIdempotencyKey } from "@/lib/idempotency";
import { useSession } from "@/store/session";

type Attempt = { signature: string; key: string };

/**
 * Start paying some charges (all from ONE landlord):
 *   POST /me/pay/ (with an Idempotency-Key) -> open checkout_url in the in-app browser
 *   -> go to the result screen, which polls the public status endpoint.
 * The same key is reused if the same submit is retried after a network error (or while the
 * server says the first request is still in progress), so a flaky network can't create two links.
 */
export function usePay() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const last = useRef<Attempt | null>(null);

  const start = async (chargeIds: string[], amount?: string) => {
    if (busy || chargeIds.length === 0) return;
    const signature = JSON.stringify([[...chargeIds].sort(), amount ?? null]);
    const key = last.current?.signature === signature ? last.current.key : newIdempotencyKey();
    last.current = { signature, key };
    setBusy(true);
    setError(null);
    try {
      const started = await tenantApi.pay(amount ? { charges: chargeIds, amount } : { charges: chargeIds }, key);
      last.current = null; // done: the next submit is a new payment
      useSession.getState().suspendLockForCheckout();
      try {
        await WebBrowser.openBrowserAsync(started.checkout_url, {
          dismissButtonStyle: "close",
          showTitle: true,
          enableBarCollapsing: true,
        });
      } catch {
        // No browser could open: the result screen still lets them check the status.
      }
      router.push({ pathname: "/pay/[reference]", params: { reference: started.reference } });
    } catch (e) {
      const retryable = e instanceof ApiError && (e.isNetwork || e.code === "request_in_progress");
      if (!retryable) last.current = null;
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return { start, busy, error, clearError: () => setError(null) };
}
