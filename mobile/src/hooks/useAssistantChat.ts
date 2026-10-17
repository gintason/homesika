import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { assistantApi, MAX_CHAT_CHARS, type AssistantReply, type ChatHistory, type ChatMessage, type PendingAction } from "@/api";
import { keys } from "@/hooks/queries";
import { ApiError, errorText } from "@/lib/api";
import { randomHex } from "@/lib/idempotency";

export type Bubble = {
  key: string;
  mine: boolean;
  text: string;
  /** Name of the Homesika team member when a person (not the assistant) replied. */
  from?: string | null;
  state: "sent" | "sending" | "failed";
  error?: string;
};

export type ChatState = { items: Bubble[]; pending: PendingAction | null; escalated: boolean };

const EMPTY: ChatState = { items: [], pending: null, escalated: false };

const live = (p: PendingAction | null | undefined) => (p && p.status === "proposed" ? p : null);

function fromMessage(m: ChatMessage): Bubble {
  return {
    key: m.id,
    mine: m.direction === "in",
    text: m.body,
    from: m.sender === "staff" ? m.sent_by_name : null,
    state: "sent",
  };
}

function fromHistory(h: ChatHistory): ChatState {
  return { items: h.messages.filter((m) => m.body.trim()).map(fromMessage), pending: live(h.pending_action), escalated: Boolean(h.escalated) };
}

function withReply(s: ChatState, reply: AssistantReply): ChatState {
  const items = reply.text.trim()
    ? [...s.items, { key: `local_${randomHex()}`, mine: false, text: reply.text, state: "sent" as const }]
    : s.items;
  return { items, pending: live(reply.pending_action), escalated: s.escalated || reply.escalated };
}

/**
 * The app chat with the assistant. State lives in the react-query cache (seeded from
 * GET /assistant/messages/?channel=app) so it survives tab switches and is wiped on sign-out.
 *
 * Duplicate sends: only one request is in flight at a time, and a retry first re-reads the history.
 * If the server already has the message (the network dropped the response, not the request), the
 * history is shown instead of posting it again. Each message also carries its own Idempotency-Key.
 */
export function useAssistantChat() {
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: keys.assistant,
    queryFn: async () => fromHistory(await assistantApi.history()),
    staleTime: Infinity,
  });
  const [busy, setBusy] = useState<null | "send" | "confirm" | "reject" | "clear">(null);
  const [error, setError] = useState<string | null>(null);
  const inflight = useRef(false);

  const current = () => qc.getQueryData<ChatState>(keys.assistant) ?? EMPTY;
  const update = (fn: (s: ChatState) => ChatState) => qc.setQueryData<ChatState>(keys.assistant, (s) => fn(s ?? EMPTY));
  const mark = (key: string, patch: Partial<Bubble>) =>
    update((s) => ({ ...s, items: s.items.map((b) => (b.key === key ? { ...b, ...patch } : b)) }));

  const begin = (kind: NonNullable<typeof busy>) => {
    if (inflight.current) return false;
    inflight.current = true;
    setBusy(kind);
    setError(null);
    return true;
  };
  const end = () => {
    inflight.current = false;
    setBusy(null);
  };

  /** Did the server already store this message? (More copies there than we know were sent.) */
  const landedOnServer = async (text: string): Promise<ChatHistory | null> => {
    const h = await assistantApi.history();
    const there = h.messages.filter((m) => m.direction === "in" && m.body.trim() === text).length;
    const known = current().items.filter((b) => b.mine && b.state === "sent" && b.text === text).length;
    return there > known ? h : null;
  };

  const deliver = async (key: string, text: string, retry: boolean) => {
    if (!begin("send")) return;
    mark(key, { state: "sending", error: undefined });
    try {
      if (retry) {
        const h = await landedOnServer(text);
        if (h) {
          update((s) => {
            const next = fromHistory(h);
            return { ...next, escalated: s.escalated || next.escalated };
          });
          return;
        }
      }
      const reply = await assistantApi.send(text, key);
      update((s) => withReply({ ...s, items: s.items.map((b) => (b.key === key ? { ...b, state: "sent" } : b)) }, reply));
    } catch (e) {
      mark(key, { state: "failed", error: errorText(e) });
    } finally {
      end();
    }
  };

  const send = (raw: string) => {
    const text = raw.trim();
    if (!text || text.length > MAX_CHAT_CHARS || inflight.current) return false;
    const key = `local_${randomHex()}`;
    update((s) => ({ ...s, items: [...s.items, { key, mine: true, text, state: "sending" }] }));
    void deliver(key, text, false);
    return true;
  };

  const retry = (key: string) => {
    const bubble = current().items.find((b) => b.key === key);
    if (bubble && bubble.state === "failed") void deliver(key, bubble.text, true);
  };

  const decide = async (decision: "confirm" | "reject") => {
    const pending = current().pending;
    if (!pending || !begin(decision)) return;
    try {
      const reply = await assistantApi.decide(pending.id, decision);
      update((s) => withReply({ ...s, pending: null }, reply));
    } catch (e) {
      setError(errorText(e));
      // Gone (expired and cleaned up, or chat cleared elsewhere): don't leave a dead card on screen.
      if (e instanceof ApiError && e.status === 404) update((s) => ({ ...s, pending: null }));
    } finally {
      end();
    }
  };

  const clear = async () => {
    if (!begin("clear")) return;
    try {
      await assistantApi.clear();
      qc.setQueryData<ChatState>(keys.assistant, EMPTY);
    } catch (e) {
      setError(errorText(e));
    } finally {
      end();
    }
  };

  return {
    state: query.data,
    loading: query.isPending && !query.error,
    loadError: query.error && !query.data ? errorText(query.error) : null,
    reload: () => query.refetch(),
    busy,
    error,
    send,
    retry,
    decide,
    clear,
  };
}
