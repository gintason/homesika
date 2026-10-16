import { useTranslation } from "react-i18next";
import { View } from "react-native";

import type { ChargeStatus } from "@/api";

import { Text } from "./Text";

export type BadgeStatus = ChargeStatus | "overdue";

const TONES: Record<BadgeStatus, { box: string; text: string }> = {
  paid: { box: "bg-success-50", text: "text-success-700" },
  part_paid: { box: "bg-warning-50", text: "text-warning-700" },
  open: { box: "bg-primary-50", text: "text-primary-700" },
  overdue: { box: "bg-danger-50", text: "text-danger-700" },
  waived: { box: "bg-surface-muted", text: "text-ink-700" },
  void: { box: "bg-surface-muted", text: "text-ink-700" },
};

/** Status chip. Colour is never the only signal: the label always says the status. */
export function Badge({ status, label }: { status: BadgeStatus; label?: string }) {
  const { t } = useTranslation();
  const tone = TONES[status];
  return (
    <View className={`self-start rounded-pill px-3 py-1 ${tone.box}`}>
      <Text variant="caption" className={`font-semibold ${tone.text}`}>
        {label ?? t(`charges.status.${status}`)}
      </Text>
    </View>
  );
}

/** Overdue wins over open / part paid. */
export function chargeBadgeStatus(c: { status: ChargeStatus; is_overdue: boolean }): BadgeStatus {
  return c.is_overdue ? "overdue" : c.status;
}
