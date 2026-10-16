import { useState } from "react";
import { Link } from "react-router";

import { Button, ConfirmDialog, DataTable, StatusBadge, TextField, chargeStatus, useToast } from "../components";
import { strings } from "../i18n";
import { api, errorText, type Query } from "../lib/api";
import { formatDate, formatDateTime } from "../lib/dates";
import { formatMoney } from "../lib/money";
import { useOrg } from "../lib/org";
import { useInvalidateOrg, useOrgQuery, usePaginatedList } from "../lib/queries";
import type { Charge, Lease, Payment } from "../lib/types";
import { channelLabel, linkClass } from "./shared";

const tc = strings.charges;

export function chargeLabel(c: Pick<Charge, "kind" | "description">): string {
  return c.description || tc.kinds[c.kind] || c.kind;
}

/** Charges (paginated) with an optional "Waive" action for outstanding ones. */
export function ChargesTable({ query, showTenant = true, empty }: { query: Query; showTenant?: boolean; empty?: { title: string; body?: string } }) {
  const { org, can } = useOrg();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const list = usePaginatedList<Charge>("/charges/", query);
  const [waiving, setWaiving] = useState<Charge | null>(null);
  const [reason, setReason] = useState("");
  const [reasonError, setReasonError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const canWaive = can("charge.manage");

  const close = () => {
    setWaiving(null);
    setReason("");
    setReasonError(null);
    setError(null);
  };

  const waive = async () => {
    if (!waiving) return;
    if (!reason.trim()) {
      setReasonError(strings.common.required);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api(`/orgs/${org.id}/charges/${waiving.id}/waive/`, { method: "POST", body: { reason: reason.trim() } });
      await invalidate();
      toast.show(tc.waived);
      close();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <DataTable
        caption={tc.title}
        rows={list.rows}
        loading={list.isLoading}
        error={list.error}
        onRetry={list.refetch}
        hasMore={list.hasMore}
        onLoadMore={list.loadMore}
        loadingMore={list.loadingMore}
        rowKey={(c) => c.id}
        empty={empty ?? { title: tc.empty, body: tc.emptyHint }}
        columns={[
          { key: "kind", header: tc.kind, cell: (c) => <span className="font-medium">{chargeLabel(c)}</span> },
          ...(showTenant
            ? [{ key: "tenant", header: strings.payments.tenant, cell: (c: Charge) => `${c.tenant_name} · ${c.property_name} ${c.unit_label}` }]
            : []),
          { key: "due", header: tc.due, cell: (c) => formatDate(c.due_date) },
          { key: "amount", header: tc.amount, align: "right", cell: (c) => formatMoney(c.amount, c.currency) },
          { key: "balance", header: tc.balance, align: "right", cell: (c) => formatMoney(c.balance, c.currency) },
          { key: "status", header: tc.status, cell: (c) => <StatusBadge status={chargeStatus(c)} /> },
          ...(canWaive
            ? [
                {
                  key: "actions",
                  header: strings.common.actions,
                  hideHeader: true,
                  cell: (c: Charge) =>
                    c.status === "open" || c.status === "part_paid" ? (
                      <Button variant="ghost" onClick={() => setWaiving(c)} aria-label={`${tc.waive}: ${chargeLabel(c)}, ${formatDate(c.due_date)}`}>
                        {tc.waive}
                      </Button>
                    ) : null,
                },
              ]
            : []),
        ]}
      />
      <ConfirmDialog
        open={waiving !== null}
        onClose={close}
        onConfirm={() => void waive()}
        title={tc.waiveTitle}
        description={
          waiving && (
            <>
              <strong>
                {chargeLabel(waiving)} · {formatMoney(waiving.balance, waiving.currency)}
              </strong>
              <br />
              {tc.waiveBody}
            </>
          )
        }
        confirmLabel={tc.waive}
        loading={busy}
        error={error}
      >
        <TextField
          label={tc.waiveReason}
          hint={tc.waiveReasonHint}
          value={reason}
          maxLength={200}
          onChange={(e) => {
            setReason(e.target.value);
            setReasonError(null);
          }}
          error={reasonError}
        />
      </ConfirmDialog>
    </>
  );
}

export function LeasesTable({ query, showTenant = true }: { query: Query; showTenant?: boolean }) {
  const { org, base, can } = useOrg();
  const q = useOrgQuery<Lease[]>("/leases/", query);
  const tl = strings.leases;
  return (
    <DataTable
      caption={tl.title}
      rows={q.data}
      loading={q.isLoading}
      error={q.error}
      onRetry={() => void q.refetch()}
      rowKey={(l) => l.id}
      empty={{
        title: tl.empty,
        body: tl.emptyHint,
        action: can("lease.manage") ? (
          <Link to={`${base}/leases/new${query.tenant ? `?tenant=${query.tenant}` : ""}`} className={linkClass}>
            {tl.new}
          </Link>
        ) : undefined,
      }}
      columns={[
        {
          key: "unit",
          header: tl.unit,
          cell: (l) => (
            <Link to={`${base}/leases/${l.id}`} className={linkClass}>
              {l.property_name} · {l.unit_label}
            </Link>
          ),
        },
        ...(showTenant ? [{ key: "tenant", header: tl.tenant, cell: (l: Lease) => l.tenant_name }] : []),
        { key: "dates", header: `${tl.startDate} – ${tl.endDate}`, cell: (l) => `${formatDate(l.start_date)} – ${formatDate(l.end_date)}` },
        {
          key: "rent",
          header: tl.rent,
          align: "right",
          cell: (l) => `${formatMoney(l.rent_amount, l.currency || org.currency)} ${tl.frequencies[l.rent_frequency].toLowerCase()}`,
        },
        { key: "balance", header: tl.balance, align: "right", cell: (l) => formatMoney(l.balance ?? "0.00", l.currency) },
        { key: "status", header: tl.status, cell: (l) => <StatusBadge status={l.status} /> },
      ]}
    />
  );
}

export function PaymentsTable({ query, showTenant = true }: { query: Query; showTenant?: boolean }) {
  const { base } = useOrg();
  const list = usePaginatedList<Payment>("/payments/", query);
  const tp = strings.payments;
  return (
    <DataTable
      caption={tp.title}
      rows={list.rows}
      loading={list.isLoading}
      error={list.error}
      onRetry={list.refetch}
      hasMore={list.hasMore}
      onLoadMore={list.loadMore}
      loadingMore={list.loadingMore}
      rowKey={(p) => p.id}
      empty={{ title: tp.empty, body: tp.emptyHint }}
      columns={[
        {
          key: "date",
          header: tp.paidAt,
          cell: (p) => (
            <Link to={`${base}/payments/${p.id}`} className={linkClass}>
              {formatDateTime(p.paid_at)}
            </Link>
          ),
        },
        ...(showTenant ? [{ key: "tenant", header: tp.tenant, cell: (p: Payment) => p.tenant_name }] : []),
        { key: "amount", header: strings.fields.amount, align: "right", cell: (p) => formatMoney(p.amount, p.currency) },
        { key: "channel", header: tp.channel, cell: (p) => channelLabel(p.channel || p.gateway) },
        { key: "receipt", header: tp.receipt, cell: (p) => p.receipt_number ?? "—" },
        {
          key: "status",
          header: strings.charges.status,
          cell: (p) => (
            <span className="flex flex-wrap justify-end gap-1 md:justify-start">
              <StatusBadge status={p.status} />
              {p.needs_review && <StatusBadge status="needs_review" />}
            </span>
          ),
        },
      ]}
    />
  );
}
