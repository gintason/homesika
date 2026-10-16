import { useState } from "react";

import { Button, ButtonLink, ConfirmDialog, DataTable, PageHeader, Select, TextField, optionsFrom, useToast } from "../../components";
import { strings } from "../../i18n";
import { api, errorText } from "../../lib/api";
import { formatDate } from "../../lib/dates";
import { formatMoney } from "../../lib/money";
import { useOrg } from "../../lib/org";
import { useInvalidateOrg, useOrgQuery, usePaginatedList } from "../../lib/queries";
import type { Expense, Property } from "../../lib/types";

const t = strings.expenses;

export function ExpensesList() {
  const { org, base, can } = useOrg();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const properties = useOrgQuery<Property[]>("/properties/");
  const [filters, setFilters] = useState({ property: "", category: "", from: "", to: "" });
  const list = usePaginatedList<Expense>("/expenses/", filters);
  const [deleting, setDeleting] = useState<Expense | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const manage = can("expense.manage");

  const remove = async () => {
    if (!deleting) return;
    setBusy(true);
    setError(null);
    try {
      await api(`/orgs/${org.id}/expenses/${deleting.id}/`, { method: "DELETE" });
      await invalidate();
      toast.show(strings.common.deleted);
      setDeleting(null);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  const add = manage ? <ButtonLink to={`${base}/expenses/new`}>{t.add}</ButtonLink> : undefined;
  const setFilter = (k: keyof typeof filters, value: string) => setFilters((f) => ({ ...f, [k]: value }));

  return (
    <>
      <PageHeader title={t.title} actions={add} />
      <fieldset className="mb-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <legend className="sr-only">{strings.common.filters}</legend>
        <Select
          label={t.property}
          value={filters.property}
          onChange={(e) => setFilter("property", e.target.value)}
          placeholder={strings.common.all}
          options={(properties.data ?? []).map((p) => ({ value: p.id, label: p.name }))}
        />
        <Select
          label={t.category}
          value={filters.category}
          onChange={(e) => setFilter("category", e.target.value)}
          placeholder={strings.common.all}
          options={optionsFrom(t.categories)}
        />
        <TextField label={t.from} type="date" value={filters.from} onChange={(e) => setFilter("from", e.target.value)} />
        <TextField label={t.to} type="date" value={filters.to} onChange={(e) => setFilter("to", e.target.value)} />
      </fieldset>
      <DataTable
        caption={t.title}
        rows={list.rows}
        loading={list.isLoading}
        error={list.error}
        onRetry={list.refetch}
        hasMore={list.hasMore}
        onLoadMore={list.loadMore}
        loadingMore={list.loadingMore}
        rowKey={(x) => x.id}
        empty={{ title: t.empty, body: t.emptyHint, action: add }}
        columns={[
          { key: "date", header: t.spentOn, cell: (x) => formatDate(x.spent_on) },
          { key: "category", header: t.category, cell: (x) => t.categories[x.category] ?? x.category },
          { key: "property", header: t.property, cell: (x) => x.property_name ?? t.general },
          { key: "vendor", header: t.vendor, cell: (x) => [x.vendor, x.description].filter(Boolean).join(" · ") || "—" },
          { key: "amount", header: strings.fields.amount, align: "right", cell: (x) => formatMoney(x.amount, x.currency) },
          ...(manage
            ? [
                {
                  key: "actions",
                  header: strings.common.actions,
                  hideHeader: true,
                  cell: (x: Expense) => (
                    <div className="flex flex-wrap justify-end gap-1">
                      <ButtonLink to={`${base}/expenses/${x.id}/edit`} variant="ghost" aria-label={`${strings.common.edit}: ${formatDate(x.spent_on)}`}>
                        {strings.common.edit}
                      </ButtonLink>
                      <Button variant="ghost" onClick={() => setDeleting(x)} aria-label={`${strings.common.delete}: ${formatDate(x.spent_on)}`}>
                        {strings.common.delete}
                      </Button>
                    </div>
                  ),
                },
              ]
            : []),
        ]}
      />
      <ConfirmDialog
        open={deleting !== null}
        onClose={() => {
          setDeleting(null);
          setError(null);
        }}
        onConfirm={() => void remove()}
        title={t.deleteTitle}
        description={t.deleteBody}
        confirmLabel={strings.common.delete}
        destructive
        loading={busy}
        error={error}
      />
    </>
  );
}
