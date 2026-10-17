import { useState } from "react";
import { Link, useSearchParams } from "react-router";

import {
  Badge,
  Banner,
  Button,
  DataTable,
  DescriptionList,
  Dialog,
  PageHeader,
  Select,
  StatusBadge,
  TextArea,
  optionsFrom,
  useToast,
  type BadgeTone,
} from "../../components";
import { strings } from "../../i18n";
import { api } from "../../lib/api";
import { formatDate, formatDateTime } from "../../lib/dates";
import { useOrg } from "../../lib/org";
import { formatPhone } from "../../lib/phone";
import { useInvalidateOrg, usePaginatedList } from "../../lib/queries";
import type { Lead, LeadStage } from "../../lib/types";
import { actionError, linkClass } from "../shared";

const t = strings.leads;

const STAGE_TONE: Record<LeadStage, BadgeTone> = {
  new: "info",
  contacted: "neutral",
  viewing_booked: "warning",
  viewed: "neutral",
  applied: "gold",
  won: "success",
  lost: "neutral",
};

export function StageBadge({ stage }: { stage: LeadStage }) {
  return <Badge tone={STAGE_TONE[stage] ?? "neutral"}>{t.stages[stage] ?? stage}</Badge>;
}

export function LeadsList() {
  const { base } = useOrg();
  const [params, setParams] = useSearchParams();
  const stage = params.get("stage") ?? "";
  const listing = params.get("listing") ?? "";
  const list = usePaginatedList<Lead>("/leads/", { stage, listing });
  const [openId, setOpenId] = useState<string | null>(null);
  const open = list.rows?.find((l) => l.id === openId) ?? null;

  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };

  return (
    <>
      <PageHeader title={t.title} description={t.intro} />
      <div className="mb-4 flex flex-wrap items-end gap-4">
        <Select
          containerClassName="w-full max-w-xs"
          label={t.stage}
          value={stage}
          placeholder={t.allStages}
          options={optionsFrom(t.stages)}
          onChange={(e) => setFilter("stage", e.target.value)}
        />
        {listing && (
          <p className="flex flex-wrap items-center gap-2 text-base text-ink-600">
            {t.filteredByListing}
            <Link to={`${base}/leads${stage ? `?stage=${stage}` : ""}`} className={linkClass}>
              {t.showAll}
            </Link>
          </p>
        )}
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
        empty={{ title: t.empty, body: t.emptyHint }}
        columns={[
          {
            key: "name",
            header: t.name,
            cell: (l) => (
              <button type="button" className={`${linkClass} min-h-touch text-left`} onClick={() => setOpenId(l.id)}>
                {l.name || t.unnamed}
              </button>
            ),
          },
          { key: "phone", header: t.phone, cell: (l) => formatPhone(l.phone_number) },
          {
            key: "listing",
            header: t.listing,
            cell: (l) =>
              l.listing ? (
                <Link to={`${base}/listings/${l.listing}`} className={linkClass}>
                  {l.listing_title}
                </Link>
              ) : (
                "—"
              ),
          },
          { key: "stage", header: t.stage, cell: (l) => <StageBadge stage={l.stage} /> },
          { key: "source", header: t.source, cell: (l) => t.sources[l.source] ?? l.source },
          { key: "received", header: t.received, cell: (l) => formatDate(l.created_at) },
        ]}
      />
      {open && <LeadDrawer key={open.id} lead={open} onClose={() => setOpenId(null)} />}
    </>
  );
}

function LeadDrawer({ lead, onClose }: { lead: Lead; onClose: () => void }) {
  const { org, can } = useOrg();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const canManage = can("listing.manage");
  const [notes, setNotes] = useState(lead.notes);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"stage" | "notes" | null>(null);

  const patch = async (body: Partial<Pick<Lead, "stage" | "notes">>, kind: "stage" | "notes") => {
    setBusy(kind);
    setError(null);
    try {
      await api<Lead>(`/orgs/${org.id}/leads/${lead.id}/`, { method: "PATCH", body });
      await invalidate();
      toast.show(kind === "stage" ? t.stageSaved : t.notesSaved);
    } catch (err) {
      setError(actionError(err));
    } finally {
      setBusy(null);
    }
  };

  return (
    <Dialog open variant="drawer" onClose={onClose} title={lead.name || t.unnamed} description={formatPhone(lead.phone_number)}>
      {error && <Banner tone="error">{error}</Banner>}
      <DescriptionList
        items={[
          { label: t.listing, value: lead.listing_title ?? "" },
          { label: t.source, value: t.sources[lead.source] ?? lead.source },
          { label: t.received, value: formatDateTime(lead.created_at) },
        ]}
      />
      <div>
        <p className="text-sm text-ink-600">{t.message}</p>
        <p className="mt-1 whitespace-pre-wrap text-base text-ink-800">{lead.message || t.noMessage}</p>
      </div>
      {canManage ? (
        <Select
          label={t.stage}
          value={lead.stage}
          options={optionsFrom(t.stages)}
          disabled={busy === "stage"}
          onChange={(e) => void patch({ stage: e.target.value as LeadStage }, "stage")}
        />
      ) : (
        <div>
          <p className="text-sm text-ink-600">{t.stage}</p>
          <StageBadge stage={lead.stage} />
        </div>
      )}
      {canManage ? (
        <div className="space-y-2">
          <TextArea label={t.notes} optional value={notes} rows={4} onChange={(e) => setNotes(e.target.value)} />
          <Button variant="secondary" loading={busy === "notes"} onClick={() => void patch({ notes: notes.trim() }, "notes")}>
            {t.saveNotes}
          </Button>
        </div>
      ) : (
        lead.notes && (
          <div>
            <p className="text-sm text-ink-600">{t.notes}</p>
            <p className="mt-1 whitespace-pre-wrap text-base text-ink-800">{lead.notes}</p>
          </div>
        )
      )}
      <section className="space-y-2">
        <h3 className="font-display text-lg font-semibold text-ink-900">{t.viewings}</h3>
        {lead.viewings.length === 0 ? (
          <p className="text-base text-ink-600">{t.noViewings}</p>
        ) : (
          <ul className="divide-y divide-surface-line">
            {lead.viewings.map((v) => (
              <li key={v.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <span>
                  {formatDateTime(v.starts_at)} · {v.listing_title}
                </span>
                <StatusBadge status={v.status} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </Dialog>
  );
}
