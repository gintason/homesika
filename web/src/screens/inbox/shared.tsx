import { Badge } from "../../components";
import { strings } from "../../i18n";
import type { Escalation } from "../../lib/types";

const t = strings.inbox;

/** Why a person is needed. Uses the ordinary danger tone; the emergency red is kept for the panic button. */
export function EscalationBadge({ escalation }: { escalation: Pick<Escalation, "reason"> }) {
  const urgent = escalation.reason === "emergency" || escalation.reason === "dispute" || escalation.reason === "payment_problem";
  return <Badge tone={urgent ? "danger" : "warning"}>{t.reasons[escalation.reason] ?? escalation.reason}</Badge>;
}

export function ReplyFlag({ canReply }: { canReply: boolean }) {
  return <Badge tone={canReply ? "success" : "neutral"}>{canReply ? t.canReply : t.templateOnly}</Badge>;
}
