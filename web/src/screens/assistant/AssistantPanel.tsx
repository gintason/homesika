import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { Banner, Button, Dialog, LinkifiedText, LoadingBlock, TextArea, cx } from "../../components";
import { fmt, strings } from "../../i18n";
import { newIdempotencyKey } from "../../lib/idempotency";
import { api, errorText } from "../../lib/api";
import { formatDateTime } from "../../lib/dates";
import type { AssistantHistory, AssistantReply, InboxMessage, PendingAction } from "../../lib/types";

const t = strings.assistant;
export const ASSISTANT_KEY = ["assistant", "web"] as const;
const EMPTY: AssistantHistory = { conversation: null, messages: [], pending_action: null };

let localId = 0;
function localMessage(direction: "in" | "out", body: string): InboxMessage {
  localId += 1;
  return {
    id: `local-${localId}`,
    direction,
    sender: direction === "in" ? "person" : "assistant",
    kind: "text",
    body,
    status: direction === "in" ? "received" : "sent",
    error: "",
    sent_by_name: null,
    created_at: new Date().toISOString(),
  };
}

/**
 * Slide-over chat with the Homesika assistant (channel "web"). Replies are plain text with links.
 * Proposed actions only run after Confirm (POST assistant/actions/{id}/confirm/).
 */
export function AssistantPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const history = useQuery({
    queryKey: ASSISTANT_KEY,
    queryFn: ({ signal }) => api<AssistantHistory>("/assistant/messages/", { query: { channel: "web" }, signal }),
    enabled: open,
    staleTime: Infinity,
  });
  const data = history.data ?? EMPTY;
  const [text, setText] = useState("");
  const [busy, setBusy] = useState<"send" | "confirm" | "reject" | "clear" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [escalated, setEscalated] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  const update = (fn: (d: AssistantHistory) => AssistantHistory) =>
    qc.setQueryData<AssistantHistory>(ASSISTANT_KEY, (old) => fn(old ?? EMPTY));

  const applyReply = (reply: AssistantReply) => {
    update((d) => ({
      conversation: reply.conversation,
      messages: reply.text ? [...d.messages, localMessage("out", reply.text)] : d.messages,
      pending_action: reply.pending_action,
    }));
    setEscalated(reply.escalated);
  };

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [data.messages.length, data.pending_action]);

  const send = async (e: FormEvent) => {
    e.preventDefault();
    const body = text.trim();
    if (!body || busy) return;
    const mine = localMessage("in", body);
    setError(null);
    setText("");
    update((d) => ({ ...d, messages: [...d.messages, mine] }));
    setBusy("send");
    try {
      applyReply(
        await api<AssistantReply>("/assistant/messages/", {
          method: "POST",
          body: { text: body, channel: "web" },
          idempotencyKey: newIdempotencyKey(),
        }),
      );
    } catch (err) {
      update((d) => ({ ...d, messages: d.messages.filter((m) => m.id !== mine.id) }));
      setText(body);
      setError(errorText(err));
    } finally {
      setBusy(null);
    }
  };

  const decide = async (action: PendingAction, decision: "confirm" | "reject") => {
    setBusy(decision);
    setError(null);
    try {
      applyReply(await api<AssistantReply>(`/assistant/actions/${action.id}/${decision}/`, { method: "POST" }));
      // A confirmed action may have changed org data (a payment link was sent, a viewing booked...).
      if (decision === "confirm") void qc.invalidateQueries({ queryKey: ["org"] });
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(null);
    }
  };

  const clear = async () => {
    setBusy("clear");
    setError(null);
    try {
      await api("/assistant/messages/", { method: "DELETE" });
      qc.setQueryData(ASSISTANT_KEY, EMPTY);
      setEscalated(false);
      setConfirmClear(false);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(null);
    }
  };

  const pending = data.pending_action?.status === "proposed" ? data.pending_action : null;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      variant="drawer"
      title={t.title}
      description={t.intro}
      footer={
        <form onSubmit={send} noValidate className="space-y-2 pb-5 md:pb-6">
          <TextArea
            label={t.inputLabel}
            hideLabel
            placeholder={t.placeholder}
            rows={2}
            maxLength={2000}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                e.currentTarget.form?.requestSubmit();
              }
            }}
          />
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-ink-600">{t.disclaimer}</p>
            <Button type="submit" loading={busy === "send"} disabled={!text.trim() || busy !== null}>
              {t.send}
            </Button>
          </div>
        </form>
      }
    >
      {history.isLoading ? (
        <LoadingBlock rows={3} />
      ) : history.error ? (
        <Banner tone="error" title={strings.errors.loadFailed} onRetry={() => void history.refetch()}>
          {errorText(history.error)}
        </Banner>
      ) : (
        <>
          {data.messages.length === 0 ? (
            <p className="text-base text-ink-600">{t.empty}</p>
          ) : (
            <ol className="space-y-3" aria-label={t.title} aria-live="polite">
              {data.messages.map((m) => {
                const mine = m.direction === "in";
                return (
                  <li key={m.id} className={cx("flex", mine ? "justify-end" : "justify-start")}>
                    <div className={cx("max-w-[90%] rounded-lg px-4 py-2", mine ? "bg-primary-600 text-white" : "bg-surface-muted text-ink-800")}>
                      <p className={cx("text-xs font-semibold", mine ? "text-primary-50" : "text-ink-600")}>{mine ? t.you : t.assistant}</p>
                      {mine ? <p className="whitespace-pre-wrap break-words">{m.body}</p> : <LinkifiedText text={m.body} />}
                    </div>
                  </li>
                );
              })}
            </ol>
          )}
          {busy === "send" && (
            <p role="status" className="text-sm text-ink-600">
              {t.thinking}
            </p>
          )}
          {pending && (
            <div role="group" aria-label={t.confirmTitle} className="space-y-3 rounded-lg border-l-4 border-gold-400 bg-gold-50 p-4">
              <p className="font-semibold text-ink-900">{t.confirmTitle}</p>
              <p className="text-base text-ink-800">{pending.summary}</p>
              <p className="text-sm text-ink-600">{fmt(t.expires, { time: formatDateTime(pending.expires_at) })}</p>
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => void decide(pending, "confirm")} loading={busy === "confirm"} disabled={busy !== null}>
                  {t.confirm}
                </Button>
                <Button variant="secondary" onClick={() => void decide(pending, "reject")} loading={busy === "reject"} disabled={busy !== null}>
                  {t.reject}
                </Button>
              </div>
            </div>
          )}
          {escalated && <Banner tone="info">{t.escalated}</Banner>}
          {error && <Banner tone="error">{error}</Banner>}
          {data.messages.length > 0 &&
            (confirmClear ? (
              <div role="group" aria-label={t.clearTitle} className="space-y-2 rounded-md bg-surface-muted p-4">
                <p className="font-semibold text-ink-900">{t.clearTitle}</p>
                <p className="text-sm text-ink-600">{t.clearBody}</p>
                <div className="flex flex-wrap gap-2">
                  <Button variant="destructive" onClick={() => void clear()} loading={busy === "clear"}>
                    {t.clear}
                  </Button>
                  <Button variant="ghost" onClick={() => setConfirmClear(false)}>
                    {strings.common.cancel}
                  </Button>
                </div>
              </div>
            ) : (
              <Button variant="ghost" onClick={() => setConfirmClear(true)}>
                {t.clear}
              </Button>
            ))}
          <div ref={endRef} />
        </>
      )}
    </Dialog>
  );
}
