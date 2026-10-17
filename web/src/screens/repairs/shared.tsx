import { Badge, type BadgeTone } from "../../components";
import { fmt, strings } from "../../i18n";
import type { TicketPriority, TicketStatus } from "../../lib/types";

const t = strings.repairs;

const STATUS_TONE: Record<TicketStatus, BadgeTone> = {
  awaiting_approval: "warning",
  approved: "info",
  assigned: "info",
  in_progress: "info",
  done: "gold",
  confirmed: "success",
  rejected: "neutral",
  cancelled: "neutral",
};

export function TicketStatusBadge({ status }: { status: TicketStatus }) {
  return <Badge tone={STATUS_TONE[status] ?? "neutral"}>{t.statuses[status] ?? status}</Badge>;
}

/** Normal and low priority aren't badged: only what needs attention stands out. */
export function PriorityBadge({ priority }: { priority: TicketPriority }) {
  if (priority === "emergency") return <Badge tone="danger">{t.priorities.emergency}</Badge>;
  if (priority === "urgent") return <Badge tone="warning">{t.priorities.urgent}</Badge>;
  return null;
}

export function VerifiedBadge() {
  return (
    <Badge tone="success">
      <span aria-hidden="true">✓ </span>
      {t.verified}
    </Badge>
  );
}

export function ratingText(avg: number | null, count: number): string {
  return avg === null ? t.noRatings : fmt(t.rating, { avg: avg.toFixed(1), count });
}
