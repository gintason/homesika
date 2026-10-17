import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useParams } from "react-router";

import { Badge, Banner, Button, Card, PageHeader, TextArea, cx, useToast } from "../../components";
import { fmt, strings } from "../../i18n";
import { api, ApiError } from "../../lib/api";
import { formatDateTime } from "../../lib/dates";
import { useIdempotencyKey } from "../../lib/idempotency";
import { useOrg } from "../../lib/org";
import { formatPhone } from "../../lib/phone";
import { orgKey, useInvalidateOrg, useOrgQuery } from "../../lib/queries";
import type { ConversationDetail, InboxMessage } from "../../lib/types";
import { QueryState, actionError } from "../shared";
import { EscalationBadge, ReplyFlag } from "./shared";

const t = strings.inbox;
/** No websockets yet: the open thread polls. */
export const THREAD_POLL_MS = 10_000;

export function ConversationView() {
  const { conversationId = "" } = useParams();
  const { base } = useOrg();
  const q = useOrgQuery<ConversationDetail>(`/conversations/${conversationId}/`, undefined, { refetchInterval: THREAD_POLL_MS });
  return (
    <>
      <PageHeader
        title={q.data ? q.data.contact_name || formatPhone(q.data.contact_phone) || t.unknownContact : t.title}
        description={q.data?.contact_name ? formatPhone(q.data.contact_phone) : undefined}
        back={{ to: `${base}/inbox`, label: t.back }}
      />
      <QueryState data={q.data} isLoading={q.isLoading} error={q.error} refetch={q.refetch}>
        {(convo) => <Thread convo={convo} />}
      </QueryState>
    </>
  );
}

function Bubble({ m }: { m: InboxMessage }) {
  const out = m.direction === "out";
  const who = m.sender === "staff" && m.sent_by_name ? m.sent_by_name : t.senders[m.sender] ?? m.sender;
  return (
    <li className={cx("flex", out ? "justify-end" : "justify-start")}>
      <div
        className={cx(
          "max-w-[85%] rounded-lg px-4 py-2",
          out ? (m.sender === "staff" ? "bg-primary-600 text-white" : "bg-primary-50 text-ink-800") : "bg-surface-muted text-ink-800",
        )}
      >
        <p className={cx("text-xs font-semibold", out && m.sender === "staff" ? "text-primary-50" : "text-ink-600")}>
          {fmt(t.sentBy, { sender: who, time: formatDateTime(m.created_at) })}
        </p>
        <p className="whitespace-pre-wrap break-words text-base">{m.body}</p>
        {m.status === "failed" && <p className={cx("text-sm font-semibold", m.sender === "staff" ? "text-white" : "text-danger-700")}>{t.failed}</p>}
      </div>
    </li>
  );
}

function Thread({ convo }: { convo: ConversationDetail }) {
  const { org, can } = useOrg();
  const toast = useToast();
  const qc = useQueryClient();
  const invalidate = useInvalidateOrg();
  const canReply = can("inbox.reply");
  const [body, setBody] = useState("");
  const [bodyError, setBodyError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [windowClosed, setWindowClosed] = useState(false);
  const [busy, setBusy] = useState<"take" | "release" | "reply" | null>(null);
  const { keyFor, reset } = useIdempotencyKey();
  const key = orgKey(org.id, `/conversations/${convo.id}/`, {});
  const replyBlocked = !convo.can_reply_freely || windowClosed;

  const run = async (kind: "take" | "release" | "reply", path: string, payload?: { body: string }) => {
    setBusy(kind);
    setError(null);
    try {
      const updated = await api<ConversationDetail>(`/orgs/${org.id}/conversations/${convo.id}/${path}`, {
        method: "POST",
        body: payload,
        idempotencyKey: payload ? keyFor(payload) : undefined,
      });
      qc.setQueryData(key, updated);
      void invalidate();
      if (kind === "reply") {
        reset();
        setBody("");
        toast.show(t.sent);
      } else {
        toast.show(kind === "take" ? t.takenOver : t.released);
      }
    } catch (err) {
      if (err instanceof ApiError && err.code === "whatsapp_window_closed") {
        setWindowClosed(true);
        void invalidate();
      } else {
        setError(actionError(err));
      }
    } finally {
      setBusy(null);
    }
  };

  const send = (e: FormEvent) => {
    e.preventDefault();
    const text = body.trim();
    if (!text) {
      setBodyError(strings.common.required);
      return;
    }
    void run("reply", "reply/", { body: text });
  };

  return (
    <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
      <Card>
        <p className="mb-4 text-sm text-ink-600">{t.autoRefresh}</p>
        {convo.messages.length === 0 ? (
          <p className="text-base text-ink-600">{t.noMessages}</p>
        ) : (
          <ol className="space-y-3" aria-label={t.title}>
            {convo.messages.map((m) => (
              <Bubble key={m.id} m={m} />
            ))}
          </ol>
        )}
        {canReply && convo.channel === "whatsapp" && (
          <form onSubmit={send} noValidate className="mt-6 space-y-3 border-t border-surface-line pt-4">
            {replyBlocked && <Banner tone="warning">{t.windowClosed}</Banner>}
            {error && <Banner tone="error">{error}</Banner>}
            <TextArea
              label={t.replyLabel}
              value={body}
              rows={3}
              maxLength={4000}
              disabled={replyBlocked}
              onChange={(e) => {
                setBody(e.target.value);
                setBodyError(null);
              }}
              error={bodyError}
            />
            <Button type="submit" loading={busy === "reply"} disabled={replyBlocked}>
              {t.send}
            </Button>
          </form>
        )}
      </Card>
      <div className="space-y-4">
        <Card>
          <div className="space-y-3">
            <div className="flex flex-wrap gap-2">
              <Badge tone={convo.status === "handoff" ? "info" : "neutral"}>{t.statuses[convo.status] ?? convo.status}</Badge>
              <ReplyFlag canReply={convo.can_reply_freely} />
            </div>
            {canReply && convo.status !== "handoff" && (
              <>
                <p className="text-sm text-ink-600">{t.takeOverHint}</p>
                <Button fullWidth loading={busy === "take"} onClick={() => void run("take", "take-over/")}>
                  {t.takeOver}
                </Button>
              </>
            )}
            {canReply && convo.status === "handoff" && (
              <Button variant="secondary" fullWidth loading={busy === "release"} onClick={() => void run("release", "release/")}>
                {t.release}
              </Button>
            )}
          </div>
        </Card>
        <Card title={t.escalations}>
          {convo.escalations.length === 0 ? (
            <p className="text-base text-ink-600">{strings.common.none}</p>
          ) : (
            <ul className="space-y-3">
              {convo.escalations.map((x) => (
                <li key={x.id} className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <EscalationBadge escalation={x} />
                    <Badge tone={x.status === "resolved" ? "neutral" : "info"}>{t.escalationStatuses[x.status] ?? x.status}</Badge>
                  </div>
                  {x.summary && <p className="text-base text-ink-800">{x.summary}</p>}
                  <p className="text-sm text-ink-600">{formatDateTime(x.created_at)}</p>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
