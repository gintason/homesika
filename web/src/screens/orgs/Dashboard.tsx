import { ButtonLink, Card, PageHeader, StatCard } from "../../components";
import { fmt, strings } from "../../i18n";
import { formatMoney } from "../../lib/money";
import { useOrg } from "../../lib/org";
import { useOrgQuery } from "../../lib/queries";
import type { Dashboard as DashboardData } from "../../lib/types";
import { QueryState } from "../shared";

const t = strings.dashboard;

export function Dashboard() {
  const { org, base, can } = useOrg();
  const q = useOrgQuery<DashboardData>("/dashboard/");
  return (
    <>
      <PageHeader title={org.name} description={t.title} />
      <QueryState {...q}>
        {(d) => (
          <div className="space-y-6">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <StatCard
                label={t.overdue}
                value={formatMoney(d.overdue_amount, d.currency)}
                tone={d.overdue_charges > 0 ? "danger" : "default"}
                detail={fmt(t.overdueCharges, { count: d.overdue_charges })}
              >
                {can("tenant.view") && (
                  <ButtonLink to={`${base}/arrears`} variant="ghost" className="mt-2 -ml-4">
                    {t.seeArrears} →
                  </ButtonLink>
                )}
              </StatCard>
              <StatCard label={t.dueSoon} value={formatMoney(d.due_next_30_days, d.currency)} />
              <StatCard
                label={t.occupancy}
                value={fmt(t.occupancyValue, { occupied: d.occupied_units, total: d.units })}
              />
            </div>
            <Card title={t.quickActions}>
              <div className="flex flex-wrap gap-3">
                {can("payment.record") && <ButtonLink to={`${base}/payments/new`}>{t.recordPayment}</ButtonLink>}
                {can("payment.link") && (
                  <ButtonLink to={`${base}/payment-links/new`} variant="secondary">
                    {t.sendLink}
                  </ButtonLink>
                )}
                {can("property.manage") && (
                  <ButtonLink to={`${base}/properties/new`} variant="secondary">
                    {t.addProperty}
                  </ButtonLink>
                )}
                {can("tenant.manage") && (
                  <ButtonLink to={`${base}/tenants/new`} variant="secondary">
                    {t.addTenant}
                  </ButtonLink>
                )}
              </div>
            </Card>
          </div>
        )}
      </QueryState>
    </>
  );
}
