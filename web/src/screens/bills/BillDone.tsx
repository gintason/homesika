import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router";

import { Banner, Button, LoadingBlock } from "../../components";
import { fmt, strings } from "../../i18n";
import { ApiError, api } from "../../lib/api";
import type { BillStatus, PublicBillStatus } from "../../lib/types";
import { PayLayout } from "../pay/PayLayout";

const t = strings.billDone;
const ATTEMPTS = 5;
const INTERVAL_MS = 2000;
const BACKOFF = 1.5;

/** Statuses that won't change by waiting a few more seconds: stop polling as soon as one arrives. */
const FINAL: ReadonlySet<BillStatus> = new Set(["delivered", "refund_pending", "refunded", "expired"]);

type State =
  | { kind: "checking" }
  | { kind: "result"; status: BillStatus; receipt: string | null }
  | { kind: "notFound" }
  | { kind: "unreachable" };

/**
 * Return page from the gateway after paying for airtime, data, TV or electricity. Public (no login).
 * Asks /bills/{ref}/status/ a few times with backoff, then explains the outcome in plain language.
 */
export function BillDone({ intervalMs = INTERVAL_MS }: { intervalMs?: number }) {
  const { reference = "" } = useParams();
  const [state, setState] = useState<State>({ kind: "checking" });
  const [round, setRound] = useState(0);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    let attempt = 0;
    let last: PublicBillStatus | null = null;
    const check = async () => {
      attempt += 1;
      try {
        const s = await api<PublicBillStatus>(`/bills/${encodeURIComponent(reference)}/status/`, { auth: false });
        if (cancelled) return;
        last = s;
        if (FINAL.has(s.status)) return setState({ kind: "result", status: s.status, receipt: s.receipt_number });
      } catch (e) {
        if (cancelled) return;
        if (e instanceof ApiError && e.status === 404) return setState({ kind: "notFound" });
        /* network blip: keep trying */
      }
      if (attempt >= ATTEMPTS) {
        setState(last ? { kind: "result", status: last.status, receipt: last.receipt_number } : { kind: "unreachable" });
      } else {
        timer.current = window.setTimeout(() => void check(), intervalMs * BACKOFF ** (attempt - 1));
      }
    };
    void check();
    return () => {
      cancelled = true;
      window.clearTimeout(timer.current);
    };
  }, [reference, round, intervalMs]);

  const checkAgain = useCallback(() => {
    setState({ kind: "checking" });
    setRound((r) => r + 1);
  }, []);

  const again = (
    <Button fullWidth onClick={checkAgain}>
      {t.checkAgain}
    </Button>
  );

  let body;
  if (state.kind === "checking") {
    body = <LoadingBlock rows={2} label={t.checking} />;
  } else if (state.kind === "notFound") {
    body = <Banner tone="warning">{t.notFound}</Banner>;
  } else if (state.kind === "unreachable") {
    body = (
      <>
        <Banner tone="error">{strings.errors.network}</Banner>
        {again}
      </>
    );
  } else {
    switch (state.status) {
      case "delivered":
        body = (
          <Banner tone="success" title={t.deliveredTitle}>
            {state.receipt && <p>{fmt(t.receiptNumber, { number: state.receipt })}</p>}
            <p>{t.deliveredBody}</p>
          </Banner>
        );
        break;
      case "processing":
        body = (
          <>
            <Banner tone="info" title={t.processingTitle}>
              {t.processingBody}
            </Banner>
            {again}
          </>
        );
        break;
      case "refund_pending":
      case "refunded":
        body = (
          <Banner tone="warning" title={t.refundTitle}>
            {state.status === "refunded" ? t.refundedBody : t.refundBody}
          </Banner>
        );
        break;
      case "expired":
        body = (
          <Banner tone="warning" title={t.expiredTitle}>
            {t.expiredBody}
          </Banner>
        );
        break;
      default:
        body = (
          <>
            <Banner tone="warning" title={t.awaitingTitle}>
              {t.awaitingBody}
            </Banner>
            {again}
          </>
        );
    }
  }
  return (
    <PayLayout title={t.title} footer={t.poweredBy}>
      {body}
    </PayLayout>
  );
}

export default BillDone;
