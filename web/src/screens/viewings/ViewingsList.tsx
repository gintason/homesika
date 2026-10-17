import { useState } from "react";
import { Link } from "react-router";

import { Banner, Button, Checkbox, DataTable, PageHeader, StatusBadge, useToast } from "../../components";
import { fmt, strings } from "../../i18n";
import { api } from "../../lib/api";
import { formatDateTime } from "../../lib/dates";
import { useOrg } from "../../lib/org";
import { formatPhone } from "../../lib/phone";
import { useInvalidateOrg, useOrgQuery } from "../../lib/queries";
import type { Viewing, ViewingStatus } from "../../lib/types";
import { actionError, linkClass } from "../shared";

const t = strings.viewings;

const ACTIONS: Array<{ status: ViewingStatus; label: string }> = [
  { status: "done", label: t.markDone },
  { status: "no_show", label: t.markNoShow },
  { status: "cancelled", label: t.cancel },
];

export function ViewingsList() {
  const { org, base, can } = useOrg();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const [upcoming, setUpcoming] = useState(true);
  const q = useOrgQuery<Viewing[]>("/viewings/", { upcoming: upcoming ? 1 : undefined });
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const canManage = can("listing.manage");

  const update = async (v: Viewing, status: ViewingStatus) => {
    setBusy(`${v.id}:${status}`);
    setError(null);
    try {
      await api<Viewing>(`/orgs/${org.id}/viewings/${v.id}/`, { method: "PATCH", body: { status } });
      await invalidate();
      toast.show(t.updated);
    } catch (err) {
      setError(actionError(err));
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <PageHeader title={t.title} description={t.intro} />
      <Checkbox label={t.upcomingOnly} checked={upcoming} onChange={(e) => setUpcoming(e.target.checked)} className="mb-2" />
      {error && <Banner tone="error" className="mb-4">{error}</Banner>}
      <DataTable
        caption={t.title}
        rows={q.data}
        loading={q.isLoading}
        error={q.error}
        onRetry={() => void q.refetch()}
        rowKey={(v) => v.id}
        empty={{ title: t.empty, body: t.emptyHint }}
        columns={[
          { key: "when", header: t.when, cell: (v) => formatDateTime(v.starts_at) },
          { key: "who", header: t.who, cell: (v) => `${v.lead_name || formatPhone(v.lead_phone)} · ${formatPhone(v.lead_phone)}` },
          {
            key: "listing",
            header: t.listing,
            cell: (v) => (
              <Link to={`${base}/listings/${v.listing}`} className={linkClass}>
                {v.listing_title}
              </Link>
            ),
          },
          { key: "status", header: t.status, cell: (v) => <StatusBadge status={v.status} /> },
          ...(canManage
            ? [
                {
                  key: "actions",
                  header: strings.common.actions,
                  hideHeader: true,
                  cell: (v: Viewing) =>
                    v.status === "booked" ? (
                      <span className="flex flex-wrap gap-1">
                        {ACTIONS.map((a) => (
                          <Button
                            key={a.status}
                            variant="ghost"
                            loading={busy === `${v.id}:${a.status}`}
                            disabled={busy !== null}
                            onClick={() => void update(v, a.status)}
                            aria-label={fmt(t.actionLabel, { action: a.label, name: v.lead_name || v.lead_phone, when: formatDateTime(v.starts_at) })}
                          >
                            {a.label}
                          </Button>
                        ))}
                      </span>
                    ) : null,
                },
              ]
            : []),
        ]}
      />
    </>
  );
}
