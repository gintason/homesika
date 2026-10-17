import { Link, useSearchParams } from "react-router";

import { ButtonLink, DataTable, PageHeader, Select } from "../../components";
import { strings } from "../../i18n";
import { formatDate } from "../../lib/dates";
import { useOrg } from "../../lib/org";
import { usePaginatedList } from "../../lib/queries";
import type { Ticket } from "../../lib/types";
import { linkClass } from "../shared";
import { PriorityBadge, TicketStatusBadge } from "./shared";

const t = strings.repairs;
const FILTERS = ["open", "awaiting_approval", "closed", "all"] as const;

export function RepairsList() {
  const { base, can } = useOrg();
  const [params, setParams] = useSearchParams();
  const raw = params.get("status") ?? "open";
  const status = (FILTERS as readonly string[]).includes(raw) ? raw : "open";
  const list = usePaginatedList<Ticket>("/tickets/", { status });

  return (
    <>
      <PageHeader
        title={t.title}
        description={t.intro}
        actions={can("maintenance.manage") ? <ButtonLink to={`${base}/repairs/new`}>{t.new}</ButtonLink> : undefined}
      />
      <div className="mb-4">
        <Select
          containerClassName="w-full max-w-xs"
          label={t.filter}
          value={status}
          options={FILTERS.map((f) => ({ value: f, label: t.filters[f] }))}
          onChange={(e) => setParams(e.target.value === "open" ? {} : { status: e.target.value }, { replace: true })}
        />
      </div>
      <DataTable
        caption={t.title}
        rows={list.rows}
        loading={list.isLoading}
        error={list.error}
        onRetry={list.refetch}
        hasMore={list.hasMore}
        onLoadMore={list.loadMore}
        loadingMore={list.loadingMore}
        rowKey={(r) => r.id}
        empty={{ title: t.empty, body: t.emptyHint }}
        columns={[
          {
            key: "problem",
            header: t.problem,
            cell: (r) => (
              <span className="flex flex-wrap items-center gap-2">
                <Link to={`${base}/repairs/${r.id}`} className={linkClass}>
                  {r.title}
                </Link>
                <PriorityBadge priority={r.priority} />
              </span>
            ),
          },
          { key: "ref", header: t.reference, cell: (r) => r.reference },
          { key: "unit", header: t.unit, cell: (r) => `${r.unit.label}, ${r.unit.property}` },
          { key: "tenant", header: t.tenant, cell: (r) => r.tenant?.full_name ?? "—" },
          { key: "status", header: t.status, cell: (r) => <TicketStatusBadge status={r.status} /> },
          { key: "artisan", header: t.artisan, cell: (r) => r.job?.artisan.display_name ?? t.noArtisan },
          { key: "reported", header: t.reported, cell: (r) => formatDate(r.created_at) },
        ]}
      />
    </>
  );
}
