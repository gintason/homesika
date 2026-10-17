import { useQueryClient } from "@tanstack/react-query";
import { router } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import { useRef, useState } from "react";

import { billsApi, type BillOrder, type BillOrderInput } from "@/api";
import i18n from "@/i18n";
import { ApiError, errorText } from "@/lib/api";
import { newIdempotencyKey } from "@/lib/idempotency";
import { toKobo } from "@/lib/money";
import { useSession } from "@/store/session";

import { keys } from "./queries";

type Attempt = { signature: string; key: string };

function sameMoney(a: string, b: string): boolean {
  try {
    return toKobo(a) === toKobo(b);
  } catch {
    return false;
  }
}

function lessThan(a: string, b: string): boolean {
  try {
    return toKobo(a) < toKobo(b);
  } catch {
    return false;
  }
}

/** Bills error codes with our own copy (anything else: the server's message). */
const BILL_CODES = ["bills_daily_limit", "bills_unavailable", "order_not_payable", "customer_not_found"] as const;

export function billErrorText(e: unknown): string {
  if (e instanceof ApiError && (BILL_CODES as readonly string[]).includes(e.code)) {
    return i18n.t(`bills.errors.${e.code as (typeof BILL_CODES)[number]}`);
  }
  return errorText(e);
}

/** A retry may safely reuse the key: the server never stored a response (network, in progress, 5xx). */
function isRetryable(e: unknown): boolean {
  return e instanceof ApiError && (e.isNetwork || e.code === "request_in_progress" || e.status >= 500);
}

/** Open the gateway checkout in the in-app browser, with the app lock paused (as for rent). */
export async function openCheckout(url: string): Promise<void> {
  useSession.getState().suspendLockForCheckout();
  try {
    await WebBrowser.openBrowserAsync(url, { dismissButtonStyle: "close", showTitle: true, enableBarCollapsing: true });
  } catch {
    // No browser could open: the status screen still lets them check and try again.
  }
}

/**
 * Bills checkout:
 *   POST /bills/orders/ (Idempotency-Key: one per submission, reused on retry of the SAME body)
 *   -> if the total is what the person already saw, open checkout_url at once; if a fee was added,
 *      return the order so the review can show amount + fee = total before they confirm
 *   -> the order status screen (polls GET /bills/orders/{id}/).
 */
export function useBillCheckout() {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [apiError, setApiError] = useState<ApiError | null>(null);
  const [order, setOrder] = useState<BillOrder | null>(null);
  const last = useRef<Attempt | null>(null);

  const pay = async (created: BillOrder) => {
    if (!created.checkout_url) {
      setError(i18n.t("bills.errors.bills_unavailable"));
      return;
    }
    await openCheckout(created.checkout_url);
    router.replace({ pathname: "/bills/order/[id]", params: { id: created.id } });
  };

  /** `shownTotal`: the amount the person agreed to (decimal string). */
  const submit = async (input: BillOrderInput, shownTotal: string) => {
    if (busy) return;
    if (order) return pay(order); // already created (fee confirmed): just open checkout
    const signature = JSON.stringify(input);
    const key = last.current?.signature === signature ? last.current.key : newIdempotencyKey("bill");
    last.current = { signature, key };
    setBusy(true);
    setError(null);
    setApiError(null);
    try {
      const created = await billsApi.createOrder(input, key);
      last.current = null; // done: a new submission gets a new key
      qc.invalidateQueries({ queryKey: keys.billOrders }).catch(() => {});
      if (sameMoney(created.total, shownTotal) || lessThan(created.total, shownTotal)) {
        await pay(created); // what they saw, or less (a free fee from an invite): never more without asking
      } else {
        setOrder(created); // a fee applies: show it and ask again
      }
    } catch (e) {
      if (!isRetryable(e)) last.current = null;
      setError(billErrorText(e));
      setApiError(e instanceof ApiError ? e : null);
    } finally {
      setBusy(false);
    }
  };

  /** Edit the form again: forget any created-but-unpaid order (it simply expires). */
  const reset = () => {
    setOrder(null);
    setError(null);
    setApiError(null);
    last.current = null;
  };

  return { submit, busy, error, apiError, order, reset };
}
