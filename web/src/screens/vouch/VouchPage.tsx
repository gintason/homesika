import { useState } from "react";
import { useParams } from "react-router";

import { Banner, Button, LoadingBlock, TextArea } from "../../components";
import { fmt, strings } from "../../i18n";
import { ApiError, api, errorText } from "../../lib/api";
import type { PublicVoucher } from "../../lib/types";
import { usePublicGet } from "../../lib/usePublicGet";
import { PayLayout } from "../pay/PayLayout";

const t = strings.vouch;

/**
 * Public page for a guarantor or reference, opened from their SMS (/v/{token}). No login: the link is
 * the only credential, and it shows only the artisan's business name and trades.
 */
export function VouchPage() {
  const { token = "" } = useParams();
  const path = `/vouch/${encodeURIComponent(token)}/`;
  const q = usePublicGet<PublicVoucher>(path);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState<"yes" | "no" | null>(null);
  const [answered, setAnswered] = useState<PublicVoucher | null>(null);
  const [error, setError] = useState<string | null>(null);

  const answer = async (confirm: boolean) => {
    setBusy(confirm ? "yes" : "no");
    setError(null);
    try {
      setAnswered(await api<PublicVoucher>(path, { method: "POST", auth: false, body: { confirm, comment: comment.trim() } }));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(null);
    }
  };

  const v = answered ?? q.data;
  if (q.loading && !v) {
    return (
      <PayLayout title={strings.app.loading}>
        <LoadingBlock rows={3} />
      </PayLayout>
    );
  }
  if (!v) {
    const invalid = q.error instanceof ApiError && q.error.status === 404;
    return (
      <PayLayout title={t.invalid}>
        {invalid ? (
          <Banner tone="warning">{t.invalid}</Banner>
        ) : (
          <Banner tone="error" onRetry={q.retry}>
            {errorText(q.error)}
          </Banner>
        )}
      </PayLayout>
    );
  }

  const guarantor = v.kind === "guarantor";
  const trades = v.trades.join(", ");
  const title = fmt(guarantor ? t.titleGuarantor : t.titleReference, { name: v.artisan_name });

  return (
    <PayLayout title={title}>
      {answered ? (
        <Banner tone="success">{answered.status === "confirmed" ? t.thanksYes : t.thanksNo}</Banner>
      ) : v.status !== "pending" ? (
        <Banner tone="info">{t.already}</Banner>
      ) : (
        <>
          <p className="text-base text-ink-800">{fmt(t.hello, { name: v.full_name })}</p>
          <p className="text-base text-ink-800">
            {fmt(guarantor ? t.introGuarantor : t.introReference, { artisan: v.artisan_name, trades })}
          </p>
          <p className="text-base text-ink-800">{guarantor ? t.meansGuarantor : t.meansReference}</p>
          {error && <Banner tone="error">{error}</Banner>}
          <TextArea label={t.comment} value={comment} rows={2} maxLength={300} onChange={(e) => setComment(e.target.value)} />
          <div className="flex flex-col gap-3">
            <Button fullWidth loading={busy === "yes"} disabled={busy !== null} onClick={() => void answer(true)}>
              {t.yes}
            </Button>
            <Button fullWidth variant="secondary" loading={busy === "no"} disabled={busy !== null} onClick={() => void answer(false)}>
              {t.no}
            </Button>
          </div>
          <p className="text-sm text-ink-600">{t.noNote}</p>
        </>
      )}
      <p className="text-sm text-ink-600">{t.privacy}</p>
    </PayLayout>
  );
}

export default VouchPage;
