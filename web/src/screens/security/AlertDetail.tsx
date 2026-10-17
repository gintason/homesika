import { useState } from "react";
import { useParams } from "react-router";

import { Badge, Button, Card, DataTable, DescriptionList, PageHeader, TextArea, useToast } from "../../components";
import { fmt, strings } from "../../i18n";
import { api } from "../../lib/api";
import { formatDateTime } from "../../lib/dates";
import { useOrg } from "../../lib/org";
import { formatPhone } from "../../lib/phone";
import { useInvalidateOrg, useOrgQuery } from "../../lib/queries";
import type { PanicAlertDetail } from "../../lib/types";
import { QueryState, actionError, linkClass } from "../shared";
import { AlertActions, AlertStatusBadge, mapUrl, seconds } from "./shared";

const t = strings.security;

export function AlertDetail() {
  const { alertId = "" } = useParams();
  const q = useOrgQuery<PanicAlertDetail>(`/alerts/${alertId}/`, undefined, { refetchInterval: 15_000 });
  return (
    <QueryState data={q.data} isLoading={q.isLoading} error={q.error} refetch={q.refetch}>
      {(alert) => <AlertView alert={alert} />}
    </QueryState>
  );
}

function AlertView({ alert }: { alert: PanicAlertDetail }) {
  const { org, base, can } = useOrg();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const m = alert.metrics;

  const addNote = async () => {
    setBusy(true);
    try {
      await api(`/orgs/${org.id}/alerts/${alert.id}/notes/`, { method: "POST", body: { note: note.trim() } });
      await invalidate();
      setNote("");
      toast.show(t.noteAdded);
    } catch (err) {
      toast.show(actionError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader
        back={{ to: `${base}/security`, label: t.title }}
        title={t.kinds[alert.kind]}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <span>
              {alert.estate_name}
              {alert.house ? ` · ${fmt(t.house, { house: alert.house })}` : ""}
            </span>
            <AlertStatusBadge status={alert.status} />
            {alert.silent && <Badge tone="warning">{t.silent}</Badge>}
          </span>
        }
        actions={<AlertActions alert={alert} />}
      />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card title={t.details}>
            <DescriptionList
              items={[
                { label: strings.estates.member.name, value: alert.raised_by_name },
                { label: strings.estates.member.phone, value: formatPhone(alert.raised_by_phone) },
                { label: t.when, value: formatDateTime(alert.created_at) },
                {
                  label: t.location,
                  value: alert.location ? (
                    <a className={linkClass} href={mapUrl(alert.location)} target="_blank" rel="noreferrer">
                      {t.map}
                    </a>
                  ) : null,
                },
                alert.false_alarms_90d > 0 && { label: t.falseAlarm, value: fmt(t.falseAlarms, { count: alert.false_alarms_90d }) },
                alert.close_note !== "" && { label: t.note, value: alert.close_note },
              ]}
            />
          </Card>
          <Card title={t.log} className="space-y-4">
            <ol className="space-y-3">
              {alert.notes.map((n) => (
                <li key={n.id} className="border-l-2 border-surface-line pl-3">
                  <p className="text-sm text-ink-600">
                    {formatDateTime(n.created_at)} · {n.author_name || "—"} ·{" "}
                    {(t.statuses as Record<string, string>)[n.kind] ?? (n.kind === "note" ? t.note : n.kind)}
                  </p>
                  {n.note && <p className="whitespace-pre-wrap text-ink-800">{n.note}</p>}
                </li>
              ))}
            </ol>
            {can("security.respond") && (
              <div className="space-y-2">
                <TextArea label={t.addNote} rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
                <Button variant="secondary" onClick={() => void addNote()} loading={busy} disabled={!note.trim()}>
                  {t.addNote}
                </Button>
              </div>
            )}
          </Card>
        </div>
        <Card title={t.delivery} className="space-y-2 text-ink-800">
          <p>{fmt(t.recipients, { count: m.recipients })}</p>
          <p>{fmt(t.staffReached, { reached: m.staff_reached, total: m.staff_total })}</p>
          <p>
            {t.channel.push}: {seconds(m.by_channel.push.first_delivery_seconds)}
          </p>
          <p>
            {t.channel.sms}: {seconds(m.by_channel.sms.first_delivery_seconds)}
          </p>
          {m.acknowledge_seconds !== null && <p>{fmt(t.ackTime, { s: Math.round(m.acknowledge_seconds) })}</p>}
        </Card>
      </div>
      <div className="mt-6">
        <DataTable
          caption={t.delivery}
          rows={alert.deliveries}
          rowKey={(r) => r.id}
          empty={{ title: t.notDelivered }}
          columns={[
            { key: "who", header: strings.estates.member.name, cell: (r) => r.name || formatPhone(r.phone_number) },
            { key: "aud", header: strings.estates.member.role, cell: (r) => t.audience[r.audience] },
            { key: "ch", header: t.delivery, cell: (r) => t.channel[r.channel] },
            { key: "st", header: strings.estates.member.status, cell: (r) => t.deliveryStatus[r.status] + (r.error ? ` (${r.error})` : "") },
            { key: "at", header: t.when, cell: (r) => formatDateTime(r.delivered_at ?? r.sent_at) },
          ]}
        />
      </div>
    </>
  );
}
