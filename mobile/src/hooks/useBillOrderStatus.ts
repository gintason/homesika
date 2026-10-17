import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { AppState } from "react-native";

import { billsApi, type BillOrder } from "@/api";
import { FINAL_STATUSES } from "@/lib/bills";

import { keys } from "./queries";

/**
 * Waits between checks: quick at first (payment confirmation), then backing off while the provider
 * delivers (≈ 1 minute in total). After that the screen offers "Check again".
 */
export const BILL_POLL_DELAYS_MS = [0, 2000, 3000, 5000, 8000, 13000, 21000];

/**
 * Poll GET /bills/orders/{id}/ (which also re-checks an unpaid order with the gateway) with backoff,
 * again when the app returns to the foreground (back from checkout) and on demand.
 * Stops at delivered / refunded / expired.
 */
export function useBillOrderStatus(id: string) {
  const qc = useQueryClient();
  const [order, setOrder] = useState<BillOrder | null>(null);
  const [checking, setChecking] = useState(true);
  const [failed, setFailed] = useState(false);
  /** When the last answer came (to tell whether an unpaid order's checkout link has run out). */
  const [checkedAt, setCheckedAt] = useState(0);
  const run = useRef(0);
  const final = useRef(false);

  const poll = useCallback(async () => {
    const n = ++run.current;
    setChecking(true);
    let lastStatus: string | null = null;
    for (const delay of BILL_POLL_DELAYS_MS) {
      if (delay) await new Promise((r) => setTimeout(r, delay));
      if (n !== run.current) return; // superseded or unmounted
      try {
        const o = await billsApi.order(id);
        if (n !== run.current) return;
        setOrder(o);
        setCheckedAt(Date.now());
        setFailed(false);
        if (o.status !== lastStatus) {
          lastStatus = o.status;
          qc.invalidateQueries({ queryKey: keys.billOrders }).catch(() => {});
        }
        if ((FINAL_STATUSES as readonly string[]).includes(o.status)) {
          final.current = true;
          break;
        }
        // Refunds take days: no point polling for one.
        if (o.status === "refund_pending") break;
      } catch {
        if (n === run.current) setFailed(true); // keep trying on the next tick
      }
    }
    if (n === run.current) setChecking(false);
  }, [id, qc]);

  useEffect(() => {
    if (!id) return;
    const runs = run;
    const first = setTimeout(poll, 0);
    const sub = AppState.addEventListener("change", (state) => {
      if (state === "active" && !final.current) poll();
    });
    return () => {
      clearTimeout(first);
      runs.current++;
      sub.remove();
    };
  }, [id, poll]);

  const linkExpired = order ? Date.parse(order.expires_at) <= checkedAt : true;
  return { order, checking, failed, linkExpired, checkAgain: poll };
}
