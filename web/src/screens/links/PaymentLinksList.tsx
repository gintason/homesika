import { useState } from "react";

import { Button, ButtonLink, ConfirmDialog, DataTable, PageHeader, Select, StatusBadge, optionsFrom, useToast } from "../../components";
import { strings } from "../../i18n";
import { api, errorText } from "../../lib/api";
import { formatDate } from "../../lib/dates";
import { formatMoney } from "../../lib/money";
import { useOrg } from "../../lib/org";
import { useInvalidateOrg, usePaginatedList } from "../../lib/queries";
import type { PaymentLink } from "../../lib/types";
import { LinkShare } from "./LinkShare";

const t = strings.links;

export function PaymentLinksList() {
  const { org, base, can } = useOrg();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const [status, setStatus] = useState("");
  const list = usePaginatedList<PaymentLink>("/payment-links/", { status });
  const [cancelling, setCancelling] = useState<PaymentLink | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const manage = can("payment.link");

  const cancel = async () => {
    if (!cancelling) return;
    setBusy(true);
    setError(null);
    try {
      await api(`/orgs/${org.id}/payment-links/${cancelling.id}/cancel/`, { method: "POST" });
      await invalidate();
      toast.show(t.cancelled);
      setCancelling(null);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  const create = manage ? <ButtonLink to={`${base}/payment-links/new`}>{t.create}</ButtonLink> : undefined;
  return (
    <>
      <PageHeader title={t.title} actions={create} />
      <div className="mb-4 max-w-xs">
        <Select label={t.status} value={status} onChange={(e) => setStatus(e.target.value)} placeholder={strings.common.all} options={optionsFrom(t.statuses)} />
      </div>
      <DataTable
        caption={t.title}
        rows={list.rows}
        loading={list.isLoading}
        error={list.error}
        onRetry={list.refetch}
        hasMore={list.hasMore}
        onLoadMore={list.loadMore}
        loadingMore={list.loadingMore}
        rowKey={(l) => l.id}
        empty={{ title: t.empty, body: t.emptyHint, action: create }}
        columns={[
          { key: "tenant", header: strings.payments.tenant, cell: (l) => <span className="font-medium">{l.tenant_name}</span> },
          { key: "amount", header: strings.fields.amount, align: "right", cell: (l) => formatMoney(l.amount, l.currency) },
          { key: "status", header: t.status, cell: (l) => <StatusBadge status={l.status} /> },
          { key: "expires", header: t.expires, cell: (l) => formatDate(l.expires_at) },
          {
            key: "actions",
            header: strings.common.actions,
            hideHeader: true,
            cell: (l) =>
              l.status === "pending" ? (
                <div className="flex flex-wrap justify-end gap-1">
                  <LinkShare url={l.url} compact />
                  {manage && (
                    <Button variant="ghost" onClick={() => setCancelling(l)} aria-label={`${t.cancel}: ${l.tenant_name}`}>
                      {t.cancel}
                    </Button>
                  )}
                </div>
              ) : null,
          },
        ]}
      />
      <ConfirmDialog
        open={cancelling !== null}
        onClose={() => {
          setCancelling(null);
          setError(null);
        }}
        onConfirm={() => void cancel()}
        title={t.cancelTitle}
        description={t.cancelBody}
        confirmLabel={t.cancel}
        destructive
        loading={busy}
        error={error}
      />
    </>
  );
}
