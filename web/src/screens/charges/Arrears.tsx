import { Link } from "react-router";

import { ButtonLink, DataTable, PageHeader, StatCard } from "../../components";
import { fmt, strings } from "../../i18n";
import { formatDate } from "../../lib/dates";
import { formatMoney } from "../../lib/money";
import { useOrg } from "../../lib/org";
import { formatPhone } from "../../lib/phone";
import { useOrgQuery } from "../../lib/queries";
import type { Arrears as ArrearsData, ArrearsRow } from "../../lib/types";
import { linkClass } from "../shared";

const t = strings.arrears;

export function Arrears() {
  const { base, can } = useOrg();
  const q = useOrgQuery<ArrearsData>("/arrears/");
  return (
    <>
      <PageHeader title={t.title} description={t.intro} />
      {q.data && (
        <div className="mb-6 max-w-sm">
          <StatCard label={t.totalOwed} value={formatMoney(q.data.total_owed, q.data.currency)} tone={q.data.results.length ? "danger" : "success"} />
        </div>
      )}
      <DataTable
        caption={t.title}
        rows={q.data?.results}
        loading={q.isLoading}
        error={q.error}
        onRetry={() => void q.refetch()}
        rowKey={(r) => r.lease}
        empty={{ title: t.empty, body: t.emptyHint }}
        columns={[
          {
            key: "tenant",
            header: strings.payments.tenant,
            cell: (r) => (
              <Link to={`${base}/tenants/${r.tenant}`} className={linkClass}>
                {r.tenant_name}
              </Link>
            ),
          },
          { key: "phone", header: strings.fields.phone, cell: (r) => <a href={`tel:${r.tenant_phone}`} className={linkClass}>{formatPhone(r.tenant_phone)}</a> },
          { key: "unit", header: strings.leases.unit, cell: (r) => `${r.property} · ${r.unit}` },
          { key: "owed", header: t.owed, align: "right", cell: (r) => <strong>{formatMoney(r.owed, q.data?.currency)}</strong> },
          { key: "oldest", header: t.oldestDue, cell: (r) => formatDate(r.oldest_due) },
          { key: "days", header: t.daysOverdue, align: "right", cell: (r) => fmt(t.days, { count: r.days_overdue }) },
          ...(can("payment.link")
            ? [
                {
                  key: "actions",
                  header: strings.common.actions,
                  hideHeader: true,
                  cell: (r: ArrearsRow) => (
                    <ButtonLink to={`${base}/payment-links/new?tenant=${r.tenant}`} variant="ghost" aria-label={`${t.sendLink}: ${r.tenant_name}`}>
                      {t.sendLink}
                    </ButtonLink>
                  ),
                },
              ]
            : []),
        ]}
      />
    </>
  );
}
