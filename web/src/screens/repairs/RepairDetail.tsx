import { useRef, useState } from "react";
import { useParams } from "react-router";

import {
  Banner,
  Button,
  Card,
  Checkbox,
  ConfirmDialog,
  DescriptionList,
  Dialog,
  EmptyState,
  LoadingBlock,
  PageHeader,
  TextArea,
  TextField,
  useToast,
} from "../../components";
import { fmt, strings } from "../../i18n";
import { api } from "../../lib/api";
import { formatDateTime } from "../../lib/dates";
import { useOrg } from "../../lib/org";
import { formatPhone } from "../../lib/phone";
import { useInvalidateOrg, useOrgQuery } from "../../lib/queries";
import type { DirectoryArtisan, Ticket, TicketAction } from "../../lib/types";
import { QueryState, actionError } from "../shared";
import { PriorityBadge, TicketStatusBadge, VerifiedBadge, ratingText } from "./shared";

const t = strings.repairs;

export function RepairDetail() {
  const { ticketId = "" } = useParams();
  const q = useOrgQuery<Ticket>(`/tickets/${ticketId}/`);
  return (
    <QueryState data={q.data} isLoading={q.isLoading} error={q.error} refetch={q.refetch}>
      {(ticket) => <RepairView ticket={ticket} />}
    </QueryState>
  );
}

type Simple = "approve" | "reject" | "resolve" | "cancel" | "confirm";

const SIMPLE: Record<
  Simple,
  { title: string; body?: string; field?: { key: "note" | "reason"; label: string; required: boolean }; done: string; destructive?: boolean }
> = {
  approve: { title: t.approveTitle, body: t.approveBody, field: { key: "note", label: t.approveNote, required: false }, done: t.approved },
  reject: { title: t.rejectTitle, field: { key: "reason", label: t.rejectReason, required: true }, done: t.rejected, destructive: true },
  resolve: { title: t.resolveTitle, field: { key: "note", label: t.resolveNote, required: true }, done: t.resolved },
  cancel: { title: t.cancelTitle, field: { key: "reason", label: t.cancelReason, required: false }, done: t.cancelled, destructive: true },
  confirm: { title: t.confirmTitle, body: t.confirmBody, done: t.confirmed },
};

const LABEL: Record<Simple, string> = {
  approve: t.approve,
  reject: t.reject,
  resolve: t.resolve,
  cancel: t.cancel,
  confirm: t.confirm,
};

function RepairView({ ticket }: { ticket: Ticket }) {
  const { org, base, can } = useOrg();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const [dialog, setDialog] = useState<Simple | "assign" | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const allowed = (a: TicketAction) => ticket.can.includes(a);
  const canApprove = can("maintenance.approve");
  const canManage = can("maintenance.manage");

  const open = (d: Simple | "assign") => {
    setText("");
    setError(null);
    setDialog(d);
  };

  const run = async (kind: Simple) => {
    const spec = SIMPLE[kind];
    setBusy(true);
    setError(null);
    try {
      await api<Ticket>(`/orgs/${org.id}/tickets/${ticket.id}/${kind}/`, {
        method: "POST",
        body: spec.field ? { [spec.field.key]: text.trim() } : undefined,
      });
      await invalidate();
      toast.show(spec.done);
      setDialog(null);
    } catch (err) {
      setError(actionError(err));
    } finally {
      setBusy(false);
    }
  };

  const buttons: Array<{ kind: Simple | "assign"; show: boolean; variant?: "primary" | "secondary" }> = [
    { kind: "approve", show: allowed("approve") && canApprove },
    { kind: "assign", show: (allowed("assign") || allowed("reassign")) && canManage },
    { kind: "confirm", show: allowed("confirm") && canManage },
    { kind: "resolve", show: allowed("resolve") && canManage, variant: "secondary" },
    { kind: "reject", show: allowed("reject") && canApprove, variant: "secondary" },
    { kind: "cancel", show: allowed("cancel") && canManage, variant: "secondary" },
  ];
  const actions = buttons
    .filter((b) => b.show)
    .map((b) => (
      <Button key={b.kind} variant={b.variant ?? "primary"} onClick={() => open(b.kind)}>
        {b.kind === "assign" ? (allowed("reassign") ? t.reassign : t.assign) : LABEL[b.kind]}
      </Button>
    ));

  const simple = dialog && dialog !== "assign" ? SIMPLE[dialog] : null;
  const missing = Boolean(simple?.field?.required && !text.trim());

  return (
    <>
      <PageHeader
        back={{ to: `${base}/repairs`, label: t.title }}
        title={ticket.title}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <span>
              {ticket.reference} · {ticket.unit.label}, {ticket.unit.property}
            </span>
            <TicketStatusBadge status={ticket.status} />
            <PriorityBadge priority={ticket.priority} />
          </span>
        }
        actions={actions.length ? actions : undefined}
      />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card title={t.details} className="space-y-4">
            <p className="whitespace-pre-wrap text-base text-ink-800">{ticket.description}</p>
            <DescriptionList
              items={[
                { label: t.category, value: t.categories[ticket.category] ?? ticket.category },
                { label: t.priority, value: t.priorities[ticket.priority] },
                { label: t.accessNotes, value: ticket.access_notes || "—" },
                {
                  label: t.tenant,
                  value: ticket.tenant ? `${ticket.tenant.full_name} · ${formatPhone(ticket.tenant.phone_number)}` : "—",
                },
                { label: t.channel, value: t.channels[ticket.channel] },
                { label: t.reported, value: formatDateTime(ticket.created_at) },
                ...(ticket.closed_reason ? [{ label: t.closedReason, value: ticket.closed_reason }] : []),
              ]}
            />
            {ticket.auto_confirmed && <p className="text-base text-ink-600">{t.autoConfirmed}</p>}
          </Card>
          <Photos ticket={ticket} canAdd={allowed("photo") && canManage} />
          <Timeline ticket={ticket} canComment={allowed("comment") && canManage} />
        </div>
        <div className="space-y-6">
          <JobCard ticket={ticket} />
          <p className="text-sm text-ink-600">{t.noPayments}</p>
        </div>
      </div>

      {simple && dialog && dialog !== "assign" && (
        <ConfirmDialog
          open
          onClose={() => setDialog(null)}
          onConfirm={() => void run(dialog)}
          title={simple.title}
          description={simple.body}
          confirmLabel={LABEL[dialog]}
          destructive={simple.destructive}
          loading={busy}
          error={error}
          confirmDisabled={missing}
        >
          {simple.field && (
            <TextArea
              label={simple.field.label}
              optional={!simple.field.required}
              value={text}
              rows={3}
              maxLength={300}
              onChange={(e) => setText(e.target.value)}
            />
          )}
        </ConfirmDialog>
      )}
      {dialog === "assign" && <AssignDialog ticket={ticket} onClose={() => setDialog(null)} />}
    </>
  );
}

function JobCard({ ticket }: { ticket: Ticket }) {
  const job = ticket.job;
  if (!job) {
    return (
      <Card title={t.job}>
        <p className="text-base text-ink-600">{t.noArtisan}</p>
      </Card>
    );
  }
  const a = job.artisan;
  return (
    <Card title={t.job} className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-display text-lg font-semibold text-ink-900">{a.display_name}</span>
        {a.is_verified && <VerifiedBadge />}
      </div>
      <p className="text-base text-ink-600">
        {ratingText(a.rating_avg, a.rating_count)} · {fmt(t.jobsDone, { count: a.jobs_completed })}
      </p>
      <DescriptionList
        items={[
          { label: t.status, value: t.jobStatuses[job.status] ?? job.status },
          ...(job.status === "offered" ? [{ label: t.acceptBy, value: formatDateTime(job.offer_expires_at) }] : []),
          ...(job.scheduled_for ? [{ label: t.visit, value: formatDateTime(job.scheduled_for) }] : []),
          ...(a.phone_number ? [{ label: t.callArtisan, value: formatPhone(a.phone_number) }] : []),
          ...(job.completion_note ? [{ label: t.completionNote, value: job.completion_note }] : []),
          ...(ticket.rating
            ? [{ label: t.tenantRating, value: `${fmt(t.stars, { score: ticket.rating.score })}${ticket.rating.comment ? ` · ${ticket.rating.comment}` : ""}` }]
            : []),
        ]}
      />
    </Card>
  );
}

function Photos({ ticket, canAdd }: { ticket: Ticket; canAdd: boolean }) {
  const { org } = useOrg();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  let report = 0;
  let done = 0;

  const upload = async (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const body = new FormData();
      body.append("image", file);
      await api(`/orgs/${org.id}/tickets/${ticket.id}/photos/`, { method: "POST", body });
      toast.show(t.photoAdded);
      await invalidate();
    } catch (err) {
      setError(actionError(err));
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  };

  return (
    <Card title={t.photos} className="space-y-4">
      {error && <Banner tone="error">{error}</Banner>}
      {ticket.photos.length === 0 ? (
        <p className="text-base text-ink-600">{t.noPhotos}</p>
      ) : (
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {ticket.photos.map((p) => {
            const alt = p.stage === "completion" ? fmt(t.photoDone, { n: ++done }) : fmt(t.photoOf, { n: ++report });
            return (
              <li key={p.id}>
                {p.url ? (
                  <a href={p.url} target="_blank" rel="noopener noreferrer" className="block">
                    <img src={p.url} alt={alt} loading="lazy" className="aspect-square w-full rounded-md object-cover" />
                  </a>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
      {canAdd && (
        <div>
          <input
            ref={input}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            className="sr-only"
            id={`photo-${ticket.id}`}
            onChange={(e) => void upload(e.target.files?.[0])}
          />
          <Button variant="secondary" loading={busy} onClick={() => input.current?.click()}>
            {t.addPhoto}
          </Button>
        </div>
      )}
    </Card>
  );
}

function Timeline({ ticket, canComment }: { ticket: Ticket; canComment: boolean }) {
  const { org } = useOrg();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const [note, setNote] = useState("");
  const [internal, setInternal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const post = async () => {
    setBusy(true);
    setError(null);
    try {
      await api(`/orgs/${org.id}/tickets/${ticket.id}/comments/`, { method: "POST", body: { note: note.trim(), internal } });
      setNote("");
      setInternal(false);
      toast.show(t.commented);
      await invalidate();
    } catch (err) {
      setError(actionError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title={t.timeline} className="space-y-4">
      <ol className="space-y-3">
        {ticket.events.map((e) => (
          <li key={e.id} className="border-l-2 border-surface-line pl-3">
            <p className="text-base text-ink-900">
              <span className="font-medium">{(t.events as Record<string, string>)[e.kind] ?? e.kind}</span>
              {e.internal && <span className="ml-2 text-sm text-ink-600">({t.internal})</span>}
            </p>
            <p className="text-sm text-ink-600">
              {formatDateTime(e.created_at)}
              {e.actor_role ? ` · ${(t.roles as Record<string, string>)[e.actor_role] ?? e.actor_role}` : ""}
              {e.actor_name ? ` · ${e.actor_name}` : ""}
            </p>
            {e.note && <p className="mt-1 whitespace-pre-wrap text-base text-ink-800">{e.note}</p>}
          </li>
        ))}
      </ol>
      {canComment && (
        <div className="space-y-2 border-t border-surface-line pt-4">
          {error && <Banner tone="error">{error}</Banner>}
          <TextArea label={t.commentLabel} value={note} rows={3} maxLength={1000} onChange={(e) => setNote(e.target.value)} />
          <Checkbox label={t.commentInternal} checked={internal} onChange={(e) => setInternal(e.target.checked)} />
          <Button variant="secondary" loading={busy} disabled={!note.trim()} onClick={() => void post()}>
            {t.send}
          </Button>
        </div>
      )}
    </Card>
  );
}

function AssignDialog({ ticket, onClose }: { ticket: Ticket; onClose: () => void }) {
  const { org } = useOrg();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const [area, setArea] = useState(ticket.unit.city);
  const [anyTrade, setAnyTrade] = useState(false);
  const [note, setNote] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const q = useOrgQuery<DirectoryArtisan[]>("/artisans/", { trade: anyTrade ? "" : ticket.category, area: area.trim() });

  const choose = async (a: DirectoryArtisan) => {
    setBusyId(a.id);
    setError(null);
    try {
      await api<Ticket>(`/orgs/${org.id}/tickets/${ticket.id}/assign/`, { method: "POST", body: { artisan: a.id, note: note.trim() } });
      await invalidate();
      toast.show(fmt(t.assigned, { name: a.display_name }));
      onClose();
    } catch (err) {
      setError(actionError(err));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <Dialog open variant="drawer" onClose={onClose} title={t.assignTitle} description={t.assignIntro}>
      {error && <Banner tone="error">{error}</Banner>}
      <div className="grid gap-3 sm:grid-cols-2">
        <TextField label={t.assignSearchArea} optional value={area} onChange={(e) => setArea(e.target.value)} />
        <Checkbox label={t.allTrades} checked={anyTrade} onChange={(e) => setAnyTrade(e.target.checked)} />
      </div>
      <TextArea label={t.assignNote} optional value={note} rows={2} maxLength={300} onChange={(e) => setNote(e.target.value)} />
      {q.isLoading ? (
        <LoadingBlock rows={3} />
      ) : q.error ? (
        <Banner tone="error" onRetry={() => void q.refetch()}>
          {actionError(q.error)}
        </Banner>
      ) : !q.data?.length ? (
        <EmptyState title={t.noArtisans} body={t.noArtisansHint} />
      ) : (
        <ul className="divide-y divide-surface-line">
          {q.data.map((a) => (
            <li key={a.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
              <div>
                <p className="flex flex-wrap items-center gap-2 text-base font-medium text-ink-900">
                  {a.display_name} {a.is_verified && <VerifiedBadge />}
                </p>
                <p className="text-sm text-ink-600">
                  {a.trades.map((x) => t.categories[x] ?? x).join(", ")} · {a.service_areas.join(", ")}
                </p>
                <p className="text-sm text-ink-600">
                  {ratingText(a.rating_avg, a.rating_count)} · {fmt(t.jobsDone, { count: a.jobs_completed })}
                  {a.jobs_with_us > 0 ? ` · ${fmt(t.usedBefore, { count: a.jobs_with_us })}` : ""}
                </p>
              </div>
              <Button
                variant="secondary"
                loading={busyId === a.id}
                disabled={busyId !== null && busyId !== a.id}
                onClick={() => void choose(a)}
                aria-label={`${t.choose} ${a.display_name}`}
              >
                {t.choose}
              </Button>
            </li>
          ))}
        </ul>
      )}
    </Dialog>
  );
}
