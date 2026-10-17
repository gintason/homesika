import { useState } from "react";

import { Badge, Button, ConfirmDialog, TextArea, useToast, type BadgeTone } from "../../components";
import { fmt, strings } from "../../i18n";
import { api } from "../../lib/api";
import { useOrg } from "../../lib/org";
import { useInvalidateOrg } from "../../lib/queries";
import type { AlertStatus, PanicAlert } from "../../lib/types";
import { actionError } from "../shared";

const t = strings.security;

// Emergency red is reserved for the residents' panic button; the desk uses the ordinary danger tone.
const TONE: Record<AlertStatus, BadgeTone> = {
  triggered: "danger",
  acknowledged: "warning",
  responding: "info",
  resolved: "success",
  false_alarm: "neutral",
  cancelled: "neutral",
};

export function AlertStatusBadge({ status }: { status: AlertStatus }) {
  return <Badge tone={TONE[status]}>{t.statuses[status]}</Badge>;
}

export function mapUrl(loc: { lat: number; lng: number }): string {
  return `https://www.google.com/maps?q=${loc.lat},${loc.lng}`;
}

type Act = "acknowledge" | "respond" | "resolve" | "false-alarm";
const OPEN: AlertStatus[] = ["triggered", "acknowledged", "responding"];

/** The buttons that move an alert on, with a note where the incident log needs one. */
export function AlertActions({ alert }: { alert: Pick<PanicAlert, "id" | "status"> }) {
  const { org, can } = useOrg();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const [act, setAct] = useState<Act | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!can("security.respond") || !OPEN.includes(alert.status)) return null;

  const post = async (kind: Act, body?: object) => {
    setBusy(true);
    setError(null);
    try {
      await api(`/orgs/${org.id}/alerts/${alert.id}/${kind}/`, { method: "POST", body });
      await invalidate();
      toast.show(t.done);
      setAct(null);
      return true;
    } catch (err) {
      const msg = actionError(err);
      setError(msg);
      if (!act) toast.show(msg);
      return false;
    } finally {
      setBusy(false);
    }
  };
  const needsNote = act === "resolve" || act === "false-alarm";
  const label: Record<Act, string> = {
    acknowledge: t.acknowledge,
    respond: t.respond,
    resolve: t.resolve,
    "false-alarm": t.falseAlarm,
  };

  return (
    <div className="flex flex-wrap gap-2">
      {alert.status === "triggered" && (
        <Button onClick={() => void post("acknowledge")} loading={busy && !act}>
          {t.acknowledge}
        </Button>
      )}
      {alert.status !== "responding" && (
        <Button
          variant={alert.status === "triggered" ? "secondary" : "primary"}
          onClick={() => {
            setNote("");
            setError(null);
            setAct("respond");
          }}
        >
          {t.respond}
        </Button>
      )}
      {(["resolve", "false-alarm"] as const).map((k) => (
        <Button
          key={k}
          variant="secondary"
          onClick={() => {
            setNote("");
            setError(null);
            setAct(k);
          }}
        >
          {label[k]}
        </Button>
      ))}
      <ConfirmDialog
        open={act !== null}
        onClose={() => setAct(null)}
        onConfirm={() => void (act && post(act, { note: note.trim() }))}
        title={act ? label[act] : ""}
        confirmLabel={act ? label[act] : ""}
        loading={busy}
        error={error}
        confirmDisabled={needsNote && !note.trim()}
      >
        <TextArea
          label={needsNote ? t.note : t.respondNote}
          hint={needsNote ? t.noteHint : undefined}
          optional={!needsNote}
          rows={3}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
      </ConfirmDialog>
    </div>
  );
}

export function seconds(s: number | null): string {
  return s === null ? t.notDelivered : fmt(t.firstDelivery, { s: Math.round(s) });
}
