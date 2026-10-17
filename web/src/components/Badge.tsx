import type { ReactNode } from "react";

import { strings } from "../i18n";
import { cx } from "./cx";

export type BadgeTone = "success" | "warning" | "danger" | "info" | "neutral" | "gold";

const TONES: Record<BadgeTone, string> = {
  success: "bg-success-50 text-success-700",
  warning: "bg-warning-50 text-warning-700",
  danger: "bg-danger-50 text-danger-700",
  info: "bg-primary-50 text-primary-700",
  neutral: "bg-surface-muted text-ink-700",
  gold: "bg-gold-50 text-gold-700",
};

export function Badge({ tone = "neutral", children }: { tone?: BadgeTone; children: ReactNode }) {
  return (
    <span className={cx("inline-flex items-center rounded-pill px-3 py-1 text-xs font-semibold", TONES[tone])}>
      {children}
    </span>
  );
}

export type Status = keyof typeof strings.status;

const STATUS_TONE: Record<Status, BadgeTone> = {
  paid: "success",
  succeeded: "success",
  active: "success",
  part_paid: "warning",
  pending: "warning",
  draft: "warning",
  needs_review: "warning",
  invited: "info",
  open: "info",
  vacant: "info",
  occupied: "neutral",
  overdue: "danger",
  failed: "danger",
  waived: "neutral",
  void: "neutral",
  expired: "neutral",
  cancelled: "neutral",
  ended: "neutral",
  terminated: "neutral",
  unavailable: "neutral",
  reversed: "neutral",
  disabled: "neutral",
  published: "success",
  let: "neutral",
  archived: "neutral",
  booked: "info",
  done: "success",
  no_show: "warning",
};

/** Status chip with a consistent colour and plain-language label (paid, part_paid, open, overdue...). */
export function StatusBadge({ status }: { status: string }) {
  const known = status in STATUS_TONE;
  return (
    <Badge tone={known ? STATUS_TONE[status as Status] : "neutral"}>
      {known ? strings.status[status as Status] : status}
    </Badge>
  );
}

/** A charge shows "Overdue" instead of open/part-paid once its due date has passed. */
export function chargeStatus(c: { status: string; is_overdue: boolean }): string {
  return c.is_overdue ? "overdue" : c.status;
}
