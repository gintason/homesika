import { useCallback, useState } from "react";
import { Link } from "react-router";

import { Badge, Banner, Button, Card, ConfirmDialog, DataTable, EmptyState, LoadingBlock, PageHeader, Select, useToast } from "../../components";
import { fmt, strings } from "../../i18n";
import { api } from "../../lib/api";
import { formatDateTime } from "../../lib/dates";
import { useOrg } from "../../lib/org";
import { formatPhone } from "../../lib/phone";
import { useInvalidateOrg, useOrgQuery, usePaginatedList } from "../../lib/queries";
import type { DeliveryReport, Estate, Paginated, PanicAlert } from "../../lib/types";
import { actionError, linkClass } from "../shared";
import { AlertActions, AlertStatusBadge, mapUrl } from "./shared";
import { beep, useDeskSocket, type DeskEvent } from "./useDeskSocket";

const t = strings.security;
const POLL_MS = 15_000;

export function SecurityDesk() {
  const estates = useOrgQuery<Paginated<Estate>>("/estates/");
  const list = estates.data?.results;
  const [estateId, setEstateId] = useState<string | null>(null);
  const current = estateId ?? list?.[0]?.id ?? null;

  if (estates.isLoading) return <LoadingBlock />;
  if (!list?.length) {
    return (
      <>
        <PageHeader title={t.title} description={t.intro} />
        <EmptyState title={strings.estates.empty} body={strings.estates.emptyHint} />
      </>
    );
  }
  return <Desk estates={list} estateId={current!} onEstate={setEstateId} />;
}

function Desk({ estates, estateId, onEstate }: { estates: Estate[]; estateId: string; onEstate: (id: string) => void }) {
  const { can } = useOrg();
  const invalidate = useInvalidateOrg();
  const open = useOrgQuery<Paginated<PanicAlert>>("/alerts/", { status: "open", estate: estateId }, { refetchInterval: POLL_MS });
  const history = usePaginatedList<PanicAlert>("/alerts/", { status: "closed", estate: estateId });
  const [announce, setAnnounce] = useState("");

  const onEvent = useCallback(
    (e: DeskEvent) => {
      if (e.type === "alert.new") {
        if (e.alert.kind !== "drill") beep();
        setAnnounce(fmt(t.newAlert, { kind: e.alert.kind_label, house: e.alert.house || e.alert.raised_by_name }));
      }
      void invalidate();
    },
    [invalidate],
  );
  const socket = useDeskSocket(estateId, onEvent);
  const alerts = open.data?.results ?? [];

  return (
    <>
      <PageHeader
        title={t.title}
        description={t.intro}
        actions={
          <span className="flex items-center gap-3">
            <Badge tone={socket === "live" ? "success" : "warning"}>{socket === "live" ? t.live : t.reconnecting}</Badge>
            {can("estate.manage") && <DrillButton estateId={estateId} />}
          </span>
        }
      />
      {/* Screen readers hear new alerts at once. */}
      <p className="sr-only" role="alert" aria-live="assertive">
        {announce}
      </p>
      {estates.length > 1 && (
        <Select
          containerClassName="mb-4 w-full max-w-xs"
          label={t.estate}
          value={estateId}
          options={estates.map((e) => ({ value: e.id, label: e.name }))}
          onChange={(e) => onEstate(e.target.value)}
        />
      )}
      <h2 className="mb-3 font-display text-lg font-semibold text-ink-900">{t.open}</h2>
      {open.error ? (
        <Banner tone="error" title={strings.errors.loadFailed} onRetry={() => void open.refetch()} />
      ) : open.isLoading ? (
        <LoadingBlock />
      ) : alerts.length === 0 ? (
        <Card>
          <p className="font-semibold text-ink-900">{t.none}</p>
          <p className="text-ink-600">{t.noneHint}</p>
        </Card>
      ) : (
        <ul className="space-y-4" aria-label={t.open}>
          {alerts.map((a) => (
            <li key={a.id}>
              <AlertCard alert={a} />
            </li>
          ))}
        </ul>
      )}
      <Report estateId={estateId} />
      <h2 className="mb-3 mt-8 font-display text-lg font-semibold text-ink-900">{t.history}</h2>
      <DataTable
        caption={t.history}
        rows={history.rows}
        loading={history.isLoading}
        error={history.error}
        onRetry={history.refetch}
        hasMore={history.hasMore}
        onLoadMore={history.loadMore}
        loadingMore={history.loadingMore}
        rowKey={(r) => r.id}
        empty={{ title: t.noHistory }}
        columns={[
          { key: "kind", header: t.details, cell: (r) => <AlertLink alert={r} /> },
          { key: "house", header: strings.estates.member.house, cell: (r) => r.house || "—" },
          { key: "status", header: strings.estates.member.status, cell: (r) => <AlertStatusBadge status={r.status} /> },
          { key: "when", header: t.when, cell: (r) => formatDateTime(r.created_at) },
        ]}
      />
    </>
  );
}

function AlertLink({ alert }: { alert: PanicAlert }) {
  const { base } = useOrg();
  return (
    <Link to={`${base}/security/${alert.id}`} className={linkClass}>
      {t.kinds[alert.kind]}
    </Link>
  );
}

function AlertCard({ alert }: { alert: PanicAlert }) {
  return (
    <Card as="article" className={alert.status === "triggered" ? "ring-2 ring-danger-500" : undefined}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h3 className="flex flex-wrap items-center gap-2 font-display text-xl font-semibold text-ink-900">
            <AlertLink alert={alert} />
            <AlertStatusBadge status={alert.status} />
            {alert.silent && <Badge tone="warning">{t.silent}</Badge>}
          </h3>
          <p className="text-lg text-ink-900">{alert.house ? fmt(t.house, { house: alert.house }) : alert.estate_name}</p>
          <p className="text-ink-700">
            {fmt(t.raisedBy, { name: alert.raised_by_name || "—", phone: formatPhone(alert.raised_by_phone) })}
          </p>
          <p className="text-sm text-ink-600">{fmt(t.raised, { time: formatDateTime(alert.created_at) })}</p>
          {alert.silent && <p className="text-sm text-warning-700">{t.silentHint}</p>}
          {alert.false_alarms_90d > 0 && <p className="text-sm text-ink-600">{fmt(t.falseAlarms, { count: alert.false_alarms_90d })}</p>}
          {alert.location && (
            <p className="text-sm">
              <a className={linkClass} href={mapUrl(alert.location)} target="_blank" rel="noreferrer">
                {t.map}
              </a>
              {alert.location.accuracy ? ` (${fmt(t.accuracy, { m: Math.round(alert.location.accuracy) })})` : ""}
            </p>
          )}
        </div>
        <AlertActions alert={alert} />
      </div>
    </Card>
  );
}

function DrillButton({ estateId }: { estateId: string }) {
  const { org } = useOrg();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const send = async () => {
    setBusy(true);
    try {
      await api(`/orgs/${org.id}/alerts/drill/`, { method: "POST", query: { estate: estateId } });
      await invalidate();
      toast.show(t.drillSent);
      setOpen(false);
    } catch (err) {
      setError(actionError(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Button
        variant="secondary"
        onClick={() => {
          setError(null);
          setOpen(true);
        }}
      >
        {t.drill}
      </Button>
      <ConfirmDialog
        open={open}
        onClose={() => setOpen(false)}
        onConfirm={() => void send()}
        title={t.drillTitle}
        description={t.drillBody}
        confirmLabel={t.drill}
        loading={busy}
        error={error}
      />
    </>
  );
}

function Report({ estateId }: { estateId: string }) {
  const q = useOrgQuery<DeliveryReport>("/alerts/report/", { estate: estateId });
  if (!q.data) return null;
  const r = q.data;
  return (
    <p className="mt-6 text-sm text-ink-600">
      {t.report}: {fmt(t.reportLine, { alerts: r.alerts, drills: r.drills, falseAlarms: r.false_alarms })}
      {r.median_first_delivery_seconds !== null && ` · ${fmt(t.median, { s: Math.round(r.median_first_delivery_seconds) })}`}
    </p>
  );
}
