import { useState } from "react";
import { Link, useParams } from "react-router";

import { Banner, Button, Card, DataTable, DescriptionList, PageHeader, StatusBadge } from "../../components";
import { strings } from "../../i18n";
import { apiBlob, errorText } from "../../lib/api";
import { formatDateTime } from "../../lib/dates";
import { saveBlob } from "../../lib/download";
import { formatMoney, isPositive } from "../../lib/money";
import { useOrg } from "../../lib/org";
import { useOrgQuery } from "../../lib/queries";
import type { Payment } from "../../lib/types";
import { QueryState, channelLabel, linkClass } from "../shared";

const t = strings.payments;

export function PaymentDetail() {
  const { paymentId = "" } = useParams();
  const { org, base } = useOrg();
  const q = useOrgQuery<Payment>(`/payments/${paymentId}/`);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const download = async (p: Payment) => {
    setDownloading(true);
    setError(null);
    try {
      // Authenticated fetch -> blob: a plain link wouldn't carry the access token.
      const { blob, filename } = await apiBlob(`/orgs/${org.id}/payments/${p.id}/receipt/`);
      saveBlob(blob, filename ?? `receipt-${p.receipt_number ?? p.id}.pdf`);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setDownloading(false);
    }
  };

  return (
    <QueryState {...q}>
      {(p) => (
        <>
          <PageHeader
            title={formatMoney(p.amount, p.currency)}
            description={
              <span className="flex flex-wrap items-center gap-2">
                <Link to={`${base}/tenants/${p.tenant}`} className={linkClass}>
                  {p.tenant_name}
                </Link>
                <StatusBadge status={p.status} />
                {p.needs_review && <StatusBadge status="needs_review" />}
              </span>
            }
            back={{ to: `${base}/payments`, label: t.title }}
            actions={
              p.receipt_number && (
                <Button onClick={() => void download(p)} loading={downloading}>
                  {t.downloadReceipt}
                </Button>
              )
            }
          />
          <div className="space-y-6">
            {error && <Banner tone="error">{error}</Banner>}
            {p.needs_review && (
              <Banner tone="warning" title={t.needsReview}>
                {p.review_reason}
              </Banner>
            )}
            <Card>
              <DescriptionList
                items={[
                  { label: t.paidAt, value: formatDateTime(p.paid_at) },
                  { label: t.channel, value: channelLabel(p.channel || p.gateway) },
                  { label: t.gateway, value: channelLabel(p.gateway) },
                  { label: t.reference, value: <span className="font-mono text-sm">{p.gateway_reference}</span> },
                  { label: t.receipt, value: p.receipt_number ?? t.noReceipt },
                  isPositive(p.unallocated_amount) ? { label: t.unallocated, value: formatMoney(p.unallocated_amount, p.currency) } : null,
                  { label: t.note, value: p.note },
                ]}
              />
            </Card>
            <Card title={t.appliedTo}>
              <DataTable
                caption={t.appliedTo}
                rows={p.applied_to}
                rowKey={(a) => a.charge}
                empty={{ title: strings.common.none }}
                columns={[
                  { key: "for", header: strings.charges.kind, cell: (a) => a.description },
                  { key: "amount", header: strings.fields.amount, align: "right", cell: (a) => formatMoney(a.amount, p.currency) },
                ]}
              />
            </Card>
          </div>
        </>
      )}
    </QueryState>
  );
}
