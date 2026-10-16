import { useState } from "react";

import { Banner, Button, Card, DataTable, EmptyState, PageHeader, Select, StatCard, TextField } from "../../components";
import { strings } from "../../i18n";
import { apiBlob, errorText } from "../../lib/api";
import { currentMonth, formatDate, formatMonth } from "../../lib/dates";
import { saveBlob } from "../../lib/download";
import { formatMoney, isPositive } from "../../lib/money";
import { useOrg } from "../../lib/org";
import { useOrgQuery } from "../../lib/queries";
import type { Property, Statement as StatementData } from "../../lib/types";
import { channelLabel, QueryState } from "../shared";

const t = strings.statement;

export function Statement() {
  const { org } = useOrg();
  const [month, setMonth] = useState(currentMonth());
  const [property, setProperty] = useState("");
  const properties = useOrgQuery<Property[]>("/properties/");
  const q = useOrgQuery<StatementData>("/statements/", { month, property }, { enabled: /^\d{4}-\d{2}$/.test(month) });
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const downloadCsv = async () => {
    setDownloading(true);
    setDownloadError(null);
    try {
      const { blob, filename } = await apiBlob(`/orgs/${org.id}/statements/`, { query: { month, property, export: "csv" } });
      saveBlob(blob, filename ?? `statement-${month}.csv`);
    } catch (err) {
      setDownloadError(errorText(err));
    } finally {
      setDownloading(false);
    }
  };

  return (
    <>
      <PageHeader
        title={t.title}
        description={formatMonth(month)}
        actions={
          <Button variant="secondary" onClick={() => void downloadCsv()} loading={downloading}>
            {t.downloadCsv}
          </Button>
        }
      />
      <fieldset className="mb-6 grid gap-4 sm:grid-cols-2 lg:max-w-2xl">
        <legend className="sr-only">{strings.common.filters}</legend>
        <TextField label={t.month} type="month" value={month} max={currentMonth()} onChange={(e) => setMonth(e.target.value)} />
        <Select
          label={t.property}
          value={property}
          onChange={(e) => setProperty(e.target.value)}
          placeholder={t.allProperties}
          options={(properties.data ?? []).map((p) => ({ value: p.id, label: p.name }))}
        />
      </fieldset>
      {downloadError && <Banner tone="error" className="mb-4">{downloadError}</Banner>}
      <QueryState {...q} isLoading={q.isLoading || q.isPending}>
        {(s) => {
          const ccy = s.currency;
          const quiet = [s.totals.billed, s.totals.collected, s.totals.expenses, s.totals.unallocated].every((x) => !isPositive(x));
          return (
            <div className="space-y-6">
              <section aria-label={strings.common.view}>
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  <StatCard label={t.billed} value={formatMoney(s.totals.billed, ccy)} />
                  <StatCard label={t.collected} value={formatMoney(s.totals.collected, ccy)} tone="success" />
                  <StatCard label={t.expenses} value={formatMoney(s.totals.expenses, ccy)} />
                  <StatCard label={t.net} value={formatMoney(s.totals.net, ccy)} />
                  <StatCard label={t.unallocated} value={formatMoney(s.totals.unallocated, ccy)} />
                  <StatCard
                    label={t.outstanding}
                    value={formatMoney(s.totals.outstanding_now, ccy)}
                    tone={isPositive(s.totals.outstanding_now) ? "danger" : "default"}
                  />
                </div>
              </section>
              {quiet ? (
                <EmptyState title={t.noActivity} body={t.noActivityHint} />
              ) : (
                <>
                  <Card title={t.byProperty}>
                    <DataTable
                      caption={t.byProperty}
                      rows={s.by_property}
                      rowKey={(r) => r.property ?? "general"}
                      columns={[
                        { key: "property", header: t.property, cell: (r) => <span className="font-medium">{r.property || t.general}</span> },
                        { key: "billed", header: t.billed, align: "right", cell: (r) => formatMoney(r.billed, ccy) },
                        { key: "collected", header: t.collected, align: "right", cell: (r) => formatMoney(r.collected, ccy) },
                        { key: "expenses", header: t.expenses, align: "right", cell: (r) => formatMoney(r.expenses, ccy) },
                        { key: "net", header: t.net, align: "right", cell: (r) => <strong>{formatMoney(r.net, ccy)}</strong> },
                      ]}
                    />
                  </Card>
                  {Object.keys(s.expenses_by_category).length > 0 && (
                    <Card title={t.byCategory}>
                      <DataTable
                        caption={t.byCategory}
                        rows={Object.entries(s.expenses_by_category)}
                        rowKey={([k]) => k}
                        columns={[
                          {
                            key: "category",
                            header: strings.expenses.category,
                            cell: ([k]) => (strings.expenses.categories as Record<string, string>)[k] ?? k,
                          },
                          { key: "amount", header: strings.fields.amount, align: "right", cell: ([, v]) => formatMoney(v, ccy) },
                        ]}
                      />
                    </Card>
                  )}
                  {s.collections.length > 0 && (
                    <Card title={t.collections}>
                      <DataTable
                        caption={t.collections}
                        rows={s.collections}
                        rowKey={(r, i) => `${i}-${r.receipt}`}
                        columns={[
                          { key: "date", header: strings.fields.date, cell: (r) => formatDate(r.date) },
                          { key: "tenant", header: strings.payments.tenant, cell: (r) => r.tenant },
                          { key: "unit", header: strings.leases.unit, cell: (r) => `${r.property} · ${r.unit}` },
                          { key: "for", header: t.for, cell: (r) => r.for },
                          { key: "channel", header: strings.payments.channel, cell: (r) => channelLabel(r.channel) },
                          { key: "receipt", header: strings.payments.receipt, cell: (r) => r.receipt || "—" },
                          { key: "amount", header: strings.fields.amount, align: "right", cell: (r) => formatMoney(r.amount, ccy) },
                        ]}
                      />
                    </Card>
                  )}
                </>
              )}
            </div>
          );
        }}
      </QueryState>
    </>
  );
}
