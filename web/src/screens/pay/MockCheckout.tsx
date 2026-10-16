import { useState } from "react";
import { useNavigate, useParams } from "react-router";

import { Banner, Button, LoadingBlock } from "../../components";
import { strings } from "../../i18n";
import { api, errorText } from "../../lib/api";
import { formatMoney } from "../../lib/money";
import { PayLayout } from "./PayLayout";
import { usePublicLink } from "./usePublicLink";

const t = strings.mock;

/** MOCK gateway only (development / staging). Clearly labelled: no real money moves. */
export function MockCheckout() {
  const { reference = "" } = useParams();
  const navigate = useNavigate();
  const { data, error, loading, retry } = usePublicLink(reference);
  const [busy, setBusy] = useState<"pay" | "fail" | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const complete = async (success: boolean) => {
    setBusy(success ? "pay" : "fail");
    setActionError(null);
    try {
      await api(`/pay/${encodeURIComponent(reference)}/mock-complete/`, {
        method: "POST",
        auth: false,
        body: { success },
      });
      navigate(`/pay/${encodeURIComponent(reference)}/done`, { state: success ? undefined : { mockFailed: true } });
    } catch (err) {
      setActionError(errorText(err));
      setBusy(null);
    }
  };

  let body;
  if (loading) body = <LoadingBlock rows={3} />;
  else if (error || !data) body = <Banner tone="error" onRetry={retry}>{errorText(error)}</Banner>;
  else if (!data.mock) body = <Banner tone="error">{t.unavailable}</Banner>;
  else
    body = (
      <div className="space-y-4">
        <div role="note" className="rounded-lg border-4 border-dashed border-warning-500 bg-warning-50 p-5 text-warning-700">
          <p className="font-display text-xl font-bold">{t.title}</p>
          <p className="mt-1 text-base">{t.body}</p>
        </div>
        <div className="rounded-lg bg-surface-card p-5 shadow-sm ring-1 ring-surface-line">
          <p className="text-base text-ink-700">{data.landlord}</p>
          <p className="font-display text-3xl font-bold text-primary-800">{formatMoney(data.amount, data.currency)}</p>
        </div>
        {actionError && <Banner tone="error">{actionError}</Banner>}
        <Button fullWidth onClick={() => void complete(true)} loading={busy === "pay"} disabled={busy !== null}>
          {t.pay}
        </Button>
        <Button fullWidth variant="secondary" onClick={() => void complete(false)} loading={busy === "fail"} disabled={busy !== null}>
          {t.fail}
        </Button>
      </div>
    );
  return <PayLayout title={t.title}>{body}</PayLayout>;
}
