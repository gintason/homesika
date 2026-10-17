import { Link, useSearchParams } from "react-router";

import { Badge, Checkbox, DataTable, PageHeader, Select, optionsFrom } from "../../components";
import { strings } from "../../i18n";
import { formatDateTime } from "../../lib/dates";
import { useOrg } from "../../lib/org";
import { formatPhone } from "../../lib/phone";
import { usePaginatedList } from "../../lib/queries";
import type { Conversation } from "../../lib/types";
import { linkClass } from "../shared";
import { EscalationBadge, ReplyFlag } from "./shared";

const t = strings.inbox;

export function InboxList() {
  const { base } = useOrg();
  const [params, setParams] = useSearchParams();
  const escalated = params.get("escalated") === "1";
  const status = params.get("status") ?? "";
  const list = usePaginatedList<Conversation>("/conversations/", { escalated: escalated ? 1 : undefined, status });

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
          label={t.status}
          value={status}
          placeholder={t.allStatuses}
          options={optionsFrom(t.statuses)}
          onChange={(e) => setFilter("status", e.target.value)}
        />
        <Checkbox label={t.escalatedOnly} checked={escalated} onChange={(e) => setFilter("escalated", e.target.checked ? "1" : "")} />
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
        rowKey={(c) => c.id}
        empty={{ title: t.empty, body: t.emptyHint }}
        columns={[
          {
            key: "contact",
            header: strings.leads.name,
            cell: (c) => (
              <span className="flex flex-col">
                <Link to={`${base}/inbox/${c.id}`} className={linkClass}>
                  {c.contact_name || formatPhone(c.contact_phone) || t.unknownContact}
                </Link>
                {c.contact_name && <span className="text-sm text-ink-600">{formatPhone(c.contact_phone)}</span>}
              </span>
            ),
          },
          {
            key: "last",
            header: t.lastActive,
            cell: (c) =>
              c.last_message ? (
                <span className="flex flex-col">
                  <span className="line-clamp-2 text-ink-800">{c.last_message.body}</span>
                  <span className="text-sm text-ink-600">{formatDateTime(c.last_message.created_at)}</span>
                </span>
              ) : (
                t.noMessages
              ),
          },
          {
            key: "flags",
            header: t.status,
            cell: (c) => (
              <span className="flex flex-wrap justify-end gap-1 md:justify-start">
                {c.open_escalation && <EscalationBadge escalation={c.open_escalation} />}
                <Badge tone={c.status === "handoff" ? "info" : "neutral"}>{t.statuses[c.status] ?? c.status}</Badge>
                <ReplyFlag canReply={c.can_reply_freely} />
              </span>
            ),
          },
        ]}
      />
    </>
  );
}
