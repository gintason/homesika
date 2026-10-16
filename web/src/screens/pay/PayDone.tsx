import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation, useParams } from "react-router";

import { Banner, Button, LoadingBlock, buttonClasses } from "../../components";
import { fmt, strings } from "../../i18n";
import { api } from "../../lib/api";
import { API_URL } from "../../lib/config";
import type { PublicStatus } from "../../lib/types";
import { PayLayout, receiptPdfUrl } from "./PayLayout";

const t = strings.pay;
const ATTEMPTS = 5;
const INTERVAL_MS = 2500;

type State = { kind: "checking" } | { kind: "paid"; receipt: string | null } | { kind: "pending" } | { kind: "closed"; status: string };

/** Return page from checkout: asks /pay/{ref}/status/ a few times (it verifies with the gateway). */
export function PayDone({ intervalMs = INTERVAL_MS }: { intervalMs?: number }) {
  const { reference = "" } = useParams();
  const location = useLocation();
  const mockFailed = (location.state as { mockFailed?: boolean } | null)?.mockFailed === true;
  const [state, setState] = useState<State>({ kind: "checking" });
  const [round, setRound] = useState(0);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    if (mockFailed) return;
    let cancelled = false;
    let attempt = 0;
    const check = async () => {
      attempt += 1;
      try {
        const s = await api<PublicStatus>(`/pay/${encodeURIComponent(reference)}/status/`, { auth: false });
        if (cancelled) return;
        if (s.status === "paid") return setState({ kind: "paid", receipt: s.receipt_number });
        if (s.status === "expired" || s.status === "cancelled") return setState({ kind: "closed", status: s.status });
      } catch {
        /* network blip: keep trying */
      }
      if (cancelled) return;
      if (attempt >= ATTEMPTS) setState({ kind: "pending" });
      else timer.current = window.setTimeout(() => void check(), intervalMs);
    };
    void check();
    return () => {
      cancelled = true;
      window.clearTimeout(timer.current);
    };
  }, [reference, round, intervalMs, mockFailed]);

  const checkAgain = useCallback(() => {
    setState({ kind: "checking" });
    setRound((r) => r + 1);
  }, []);

  const back = (
    <Link to={`/pay/${encodeURIComponent(reference)}`} className={buttonClasses("ghost", true)}>
      {t.backToLink}
    </Link>
  );

  let body;
  if (mockFailed) {
    body = (
      <>
        <Banner tone="error" title={t.notPaidTitle}>
          {strings.mock.failed}
        </Banner>
        {back}
      </>
    );
  } else if (state.kind === "checking") {
    body = <LoadingBlock rows={2} label={t.checking} />;
  } else if (state.kind === "paid") {
    body = (
      <>
        <Banner tone="success" title={t.paidTitle}>
          {state.receipt && fmt(t.receiptNumber, { number: state.receipt })}
        </Banner>
        <a href={receiptPdfUrl(API_URL, reference)} className={buttonClasses("primary", true)} target="_blank" rel="noopener">
          {t.downloadReceipt}
        </a>
      </>
    );
  } else if (state.kind === "pending") {
    body = (
      <>
        <Banner tone="warning" title={t.processingTitle}>
          {t.processingBody}
        </Banner>
        <Button fullWidth onClick={checkAgain}>
          {t.checkAgain}
        </Button>
        {back}
      </>
    );
  } else {
    body = (
      <>
        <Banner tone="warning" title={t.notPaidTitle}>
          {state.status === "expired" ? t.expired : t.cancelled}
        </Banner>
        {back}
      </>
    );
  }
  return <PayLayout title={t.doneTitle}>{body}</PayLayout>;
}
