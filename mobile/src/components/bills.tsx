import { Ionicons } from "@expo/vector-icons";
import { useTranslation } from "react-i18next";
import { Pressable, View } from "react-native";

import type { BillCategory, BillOrderStatus, BillPlan } from "@/api";
import { BILL_CATEGORIES, CATEGORY_ICONS, STATUS_BADGE } from "@/lib/bills";
import { formatMoney } from "@/lib/money";
import tokens from "@/theme/tokens";

import { Badge } from "./Badge";
import { Text } from "./Text";

/** Four big tiles (icon + label), two per row; each ≥ 48 tall and wraps at large text sizes. */
export function BillCategoryTiles({ onPick, compact = false }: { onPick: (c: BillCategory) => void; compact?: boolean }) {
  const { t } = useTranslation();
  return (
    <View className="flex-row flex-wrap gap-3">
      {BILL_CATEGORIES.map((c) => (
        <Pressable
          key={c}
          onPress={() => onPick(c)}
          accessibilityRole="button"
          accessibilityLabel={t(`bills.category.${c}`)}
          accessibilityHint={t(`bills.categoryHint.${c}`)}
          className={`min-h-12 grow basis-[45%] items-center justify-center gap-2 rounded-lg border border-surface-line bg-surface-card px-3 active:bg-surface-muted ${compact ? "py-3" : "py-5"}`}
        >
          <View className="h-12 w-12 items-center justify-center rounded-full bg-sky-50">
            <Ionicons name={CATEGORY_ICONS[c]} size={26} color={tokens.color.primary[600]} />
          </View>
          <Text variant="label" className="text-center">
            {t(`bills.category.${c}`)}
          </Text>
        </Pressable>
      ))}
    </View>
  );
}

type Choice = { value: string; label: string };

/** A single-choice row of pills (network, provider, DisCo, meter type, quick amounts). */
export function ChoiceChips({
  label,
  choices,
  value,
  onChange,
  hideLabel = false,
}: {
  label: string;
  choices: Choice[];
  value: string | null;
  onChange: (value: string) => void;
  hideLabel?: boolean;
}) {
  return (
    <View className="gap-2">
      {hideLabel ? null : <Text variant="label">{label}</Text>}
      <View className="flex-row flex-wrap gap-2" accessibilityRole="radiogroup" accessibilityLabel={label}>
        {choices.map((c) => {
          const selected = c.value === value;
          return (
            <Pressable
              key={c.value}
              onPress={() => onChange(c.value)}
              accessibilityRole="radio"
              accessibilityState={{ selected, checked: selected }}
              accessibilityLabel={c.label}
              className={`min-h-12 min-w-12 items-center justify-center rounded-pill border-2 px-4 py-2 ${selected ? "border-primary-600 bg-primary-600" : "border-ink-400 bg-white active:bg-surface-muted"}`}
            >
              <Text variant="label" className={`text-center ${selected ? "text-white" : "text-ink-800"}`}>
                {c.label}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

/** Data bundles / TV bouquets: one per row with the price and validity. */
export function PlanList({
  label,
  plans,
  value,
  onChange,
}: {
  label: string;
  plans: BillPlan[];
  value: string | null;
  onChange: (id: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <View className="gap-2">
      <Text variant="label">{label}</Text>
      <View className="gap-2" accessibilityRole="radiogroup" accessibilityLabel={label}>
        {plans.map((p) => {
          const selected = p.id === value;
          const price = p.price ? formatMoney(p.price) : t("bills.youChoose");
          const validity = p.validity_days
            ? t(p.validity_days === 1 ? "bills.validityOne" : "bills.validityMany", { count: p.validity_days })
            : "";
          return (
            <Pressable
              key={p.id}
              onPress={() => onChange(p.id)}
              accessibilityRole="radio"
              accessibilityState={{ selected, checked: selected }}
              accessibilityLabel={[p.name, price, validity].filter(Boolean).join(", ")}
              className={`min-h-12 flex-row items-center gap-3 rounded-md border-2 px-4 py-3 ${selected ? "border-primary-600 bg-primary-50" : "border-surface-line bg-white active:bg-surface-muted"}`}
            >
              <Ionicons
                name={selected ? "radio-button-on" : "radio-button-off"}
                size={22}
                color={selected ? tokens.color.primary[600] : tokens.color.ink[500]}
              />
              <View className="flex-1 gap-1">
                <Text variant="label">{p.name}</Text>
                {validity ? <Text variant="caption">{validity}</Text> : null}
              </View>
              <Text variant="label" className="font-display">
                {price}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

/** "Label .......... value" for the review and receipt summaries; wraps at large text sizes. */
export function SummaryRow({ label, value, strong = false }: { label: string; value: string; strong?: boolean }) {
  return (
    <View className="flex-row flex-wrap items-start justify-between gap-x-4 gap-y-1" accessible accessibilityLabel={`${label}: ${value}`}>
      <Text className="text-ink-600">{label}</Text>
      <Text variant={strong ? "heading" : "label"} className="shrink text-right">
        {value}
      </Text>
    </View>
  );
}

export function BillStatusBadge({ status }: { status: BillOrderStatus }) {
  const { t } = useTranslation();
  return <Badge status={STATUS_BADGE[status]} label={t(`bills.status.${status}`)} />;
}
