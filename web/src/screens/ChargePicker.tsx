import { useQuery } from "@tanstack/react-query";

import { Banner, Checkbox, LoadingBlock } from "../components";
import { fmt, strings } from "../i18n";
import { errorText } from "../lib/api";
import { formatDate } from "../lib/dates";
import { formatMoney } from "../lib/money";
import { useOrg } from "../lib/org";
import { fetchAll, orgKey } from "../lib/queries";
import type { Charge } from "../lib/types";
import { chargeLabel } from "./tables";

export function useOutstandingCharges(tenantId: string) {
  const { org } = useOrg();
  return useQuery({
    queryKey: orgKey(org.id, "/charges/", "outstanding-all", tenantId),
    queryFn: () => fetchAll<Charge>(`/orgs/${org.id}/charges/`, { tenant: tenantId, status: "outstanding" }),
    enabled: Boolean(tenantId),
  });
}

/** Tick a tenant's unpaid charges (for a manual payment or a payment link). */
export function ChargePicker({
  tenantId,
  selected,
  onChange,
  legend,
  hint,
  error,
}: {
  tenantId: string;
  selected: string[];
  onChange: (ids: string[], charges: Charge[]) => void;
  legend: string;
  hint?: string;
  error?: string;
}) {
  const q = useOutstandingCharges(tenantId);
  const tp = strings.payments;
  if (!tenantId) return <p className="text-base text-ink-600">{tp.pickTenantFirst}</p>;
  if (q.isLoading) return <LoadingBlock rows={2} />;
  if (q.error || !q.data) {
    return (
      <Banner tone="error" onRetry={() => void q.refetch()}>
        {errorText(q.error)}
      </Banner>
    );
  }
  const charges = q.data;
  const toggle = (id: string, on: boolean) => {
    const ids = on ? [...selected, id] : selected.filter((x) => x !== id);
    onChange(ids, charges.filter((c) => ids.includes(c.id)));
  };
  return (
    <fieldset className="space-y-1" aria-describedby={error ? "charge-picker-error" : undefined}>
      <legend className="text-sm font-medium text-ink-800">{legend}</legend>
      {hint && <p className="text-sm text-ink-600">{hint}</p>}
      {charges.length === 0 ? (
        <p className="py-2 text-base text-ink-600">{tp.noOutstanding}</p>
      ) : (
        <ul className="divide-y divide-surface-line rounded-md border border-surface-line px-3">
          {charges.map((c) => (
            <li key={c.id}>
              <Checkbox
                checked={selected.includes(c.id)}
                onChange={(e) => toggle(c.id, e.target.checked)}
                label={
                  <span>
                    <span className="font-medium">{chargeLabel(c)}</span> · {c.property_name} {c.unit_label} ·{" "}
                    {fmt(strings.pay.due, { date: formatDate(c.due_date) })} ·{" "}
                    <strong>{formatMoney(c.balance, c.currency)}</strong>
                    {c.is_overdue && <span className="text-danger-700"> ({strings.charges.overdue})</span>}
                  </span>
                }
              />
            </li>
          ))}
        </ul>
      )}
      {error && (
        <p id="charge-picker-error" className="text-sm font-medium text-danger-700">
          {error}
        </p>
      )}
    </fieldset>
  );
}
