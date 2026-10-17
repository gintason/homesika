import { useEffect, useRef, useState } from "react";

import { API_URL } from "../../lib/config";
import { refreshAccess, session } from "../../lib/session";
import type { DeskAlert } from "../../lib/types";

export type DeskEvent = { type: "alert.new" | "alert.updated"; alert: DeskAlert };
export type SocketState = "live" | "connecting";

/** ws(s)://<api host>/ws/estates/<id>/desk/ (same host as the page when VITE_API_URL is empty). */
export function deskSocketUrl(estateId: string, origin = window.location.origin): string {
  return `${(API_URL || origin).replace(/^http/, "ws")}/ws/estates/${estateId}/desk/`;
}

const PING_MS = 25_000;
const MAX_BACKOFF_MS = 30_000;

/**
 * Live security-desk events for one estate. The token goes in the first message, not the URL. On a drop
 * it reconnects with backoff; the desk also polls, so nothing is missed while it's "connecting".
 */
export function useDeskSocket(estateId: string | null, onEvent: (e: DeskEvent) => void): SocketState {
  const [state, setState] = useState<SocketState>("connecting");
  const handler = useRef(onEvent);
  useEffect(() => {
    handler.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    if (!estateId || typeof WebSocket === "undefined") return;
    let ws: WebSocket | null = null;
    let stopped = false;
    let backoff = 2_000;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let ping: ReturnType<typeof setInterval> | undefined;

    const connect = async () => {
      if (!session.getAccess()) await refreshAccess();
      if (stopped) return;
      ws = new WebSocket(deskSocketUrl(estateId));
      ws.onopen = () => ws?.send(JSON.stringify({ type: "auth", token: session.getAccess() ?? "" }));
      ws.onmessage = (msg) => {
        let data: { type?: string; alert?: DeskAlert };
        try {
          data = JSON.parse(String(msg.data)) as typeof data;
        } catch {
          return;
        }
        if (data.type === "ready") {
          backoff = 2_000;
          setState("live");
          ping = setInterval(() => ws?.send(JSON.stringify({ type: "ping" })), PING_MS);
        } else if ((data.type === "alert.new" || data.type === "alert.updated") && data.alert) {
          handler.current({ type: data.type, alert: data.alert });
        }
      };
      ws.onclose = (ev) => {
        clearInterval(ping);
        setState("connecting");
        if (stopped) return;
        // 4401/4403: the token was refused (expired). Refresh it before trying again.
        if (ev.code === 4401 || ev.code === 4403) void refreshAccess();
        retry = setTimeout(() => void connect(), backoff);
        backoff = Math.min(backoff * 2, MAX_BACKOFF_MS);
      };
    };
    void connect();
    return () => {
      stopped = true;
      clearTimeout(retry);
      clearInterval(ping);
      ws?.close();
    };
  }, [estateId]);

  return state;
}

/** A short two-tone beep for a new alert (silently skipped where audio isn't allowed). */
export function beep() {
  try {
    const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctx) return;
    const ctx = new Ctx();
    [880, 660, 880].forEach((freq, i) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.frequency.value = freq;
      gain.gain.value = 0.2;
      osc.connect(gain).connect(ctx.destination);
      osc.start(ctx.currentTime + i * 0.25);
      osc.stop(ctx.currentTime + i * 0.25 + 0.2);
    });
  } catch {
    // no audio: the on-screen alert and the push/SMS still reach staff
  }
}
