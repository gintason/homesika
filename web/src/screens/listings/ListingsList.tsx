import { Link, useSearchParams } from "react-router";

import { ButtonLink, DataTable, PageHeader, Select, StatusBadge, optionsFrom } from "../../components";
import { fmt, strings } from "../../i18n";
import { listingPrice } from "../../lib/listings";
import { useOrg } from "../../lib/org";
import { usePaginatedList } from "../../lib/queries";
import type { Listing } from "../../lib/types";
import { linkClass } from "../shared";

const t = strings.listings;

export function ListingsList() {
  const { base, can } = useOrg();
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "";
  const list = usePaginatedList<Listing>("/listings/", { status });
  const add = can("listing.manage") ? <ButtonLink to={`${base}/listings/new`}>{t.add}</ButtonLink> : undefined;

  return (
    <>
      <PageHeader title={t.title} actions={add} />
      <div className="mb-4 max-w-xs">
        <Select
          label={t.status}
          value={status}
          placeholder={t.allStatuses}
          options={optionsFrom(t.statuses)}
          onChange={(e) => setParams(e.target.value ? { status: e.target.value } : {}, { replace: true })}
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
        rowKey={(l) => l.id}
        empty={{ title: t.empty, body: t.emptyHint, action: status ? undefined : add }}
        columns={[
          {
            key: "title",
            header: t.listingTitle,
            cell: (l) => (
              <Link to={`${base}/listings/${l.id}`} className={linkClass}>
                {l.title}
              </Link>
            ),
          },
          { key: "area", header: t.area, cell: (l) => [l.area, l.city].filter(Boolean).join(", ") },
          { key: "rent", header: t.rent, align: "right", cell: (l) => listingPrice(l) },
          { key: "status", header: t.status, cell: (l) => <StatusBadge status={l.status} /> },
          {
            key: "leads",
            header: t.leads,
            align: "right",
            cell: (l) =>
              l.lead_count > 0 ? (
                <Link to={`${base}/leads?listing=${l.id}`} className={linkClass}>
                  {fmt(t.leadCount, { count: l.lead_count })}
                </Link>
              ) : (
                fmt(t.leadCount, { count: 0 })
              ),
          },
        ]}
      />
    </>
  );
}
