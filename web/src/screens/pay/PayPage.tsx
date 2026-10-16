import { useState } from "react";
import { Link, useParams } from "react-router";

import { Banner, Button, LoadingBlock } from "../../components";
import { fmt, strings } from "../../i18n";
import { api, errorText } from "../../lib/api";
import { browser } from "../../lib/browser";
import { formatDate } from "../../lib/dates";
import { formatMoney } from "../../lib/money";
import { PayLayout } from "./PayLayout";
import { usePublicLink } from "./usePublicLink";

const t = strings.pay;

export function PayPage() {
  const { reference = "" } = useParams();
  const { data, error, loading, retry } = usePublicLink(reference);
  const [paying, setPaying] = useState(false);
  const [payError, setPayError] = useState<string | null>(null);

  const pay = async () => {
    setPaying(true);
    setPayError(null);
    try {
      const { checkout_url } = await api<{ checkout_url: string; gateway: string }>(
        `/pay/${encodeURIComponent(reference)}/checkout/`,
        { method: "POST", auth: false },
      );
      browser.assign(checkout_url);
    } catch (err) {
      setPayError(errorText(err));
      setPaying(false);
    }
  };

  let body;
  if (loading) body = <LoadingBlock rows={4} />;
  else if (error?.status === 404) body = <Banner tone="error">{t.notFound}</Banner>;
  else if (error || !data)
    body = (
      <Banner tone="error" onRetry={retry}>
        {errorText(error)}
      </Banner>
    );
  else {
    body = (
      <div className="space-y-4 rounded-lg bg-surface-card p-5 shadow-sm ring-1 ring-surface-line">
        <div>
          <p className="text-lg text-ink-800">{fmt(t.greeting, { name: data.tenant_first_name })}</p>
          <p className="text-base text-ink-700">{fmt(t.requestFrom, { landlord: data.landlord })}</p>
          {data.description && <p className="mt-1 text-base text-ink-700">{data.description}</p>}
        </div>
        {data.items.length > 0 && (
          <div>
            <h2 className="text-sm font-semibold text-ink-600">{t.items}</h2>
            <ul className="mt-2 divide-y divide-surface-line">
              {data.items.map((item, i) => (
                <li key={i} className="py-2 text-base text-ink-800">
                  {item.description} · {t.unit} {item.unit}
                  <span className="block text-sm text-ink-600">{fmt(t.due, { date: formatDate(item.due_date) })}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        <div className="border-t-2 border-gold-400 pt-3">
          <p className="text-sm text-ink-600">{t.total}</p>
          <p className="font-display text-3xl font-bold text-primary-800">{formatMoney(data.amount, data.currency)}</p>
        </div>
        {data.status === "pending" && (
          <>
            {payError && <Banner tone="error">{payError}</Banner>}
            <Button fullWidth onClick={() => void pay()} loading={paying}>
              {paying ? t.redirecting : fmt(t.payNow, { amount: formatMoney(data.amount, data.currency) })}
            </Button>
            <p className="text-sm text-ink-600">{t.secure}</p>
            <p className="text-sm text-ink-600">{fmt(t.expiresOn, { date: formatDate(data.expires_at) })}</p>
          </>
        )}
        {data.status === "paid" && (
          <Banner tone="success" title={t.paid}>
            <Link to={`/pay/${encodeURIComponent(reference)}/receipt`} className="font-semibold underline underline-offset-4">
              {t.downloadReceipt}
            </Link>
          </Banner>
        )}
        {data.status === "expired" && <Banner tone="warning">{t.expired}</Banner>}
        {data.status === "cancelled" && <Banner tone="warning">{t.cancelled}</Banner>}
      </div>
    );
  }
  return <PayLayout title={t.title}>{body}</PayLayout>;
}
