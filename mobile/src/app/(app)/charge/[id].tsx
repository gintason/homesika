import { useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { View } from "react-native";

import { Badge, Banner, Button, Card, chargeBadgeStatus, MoneyText, Screen, SkeletonCard, Text, TextField } from "@/components";
import { useCharge } from "@/hooks/queries";
import { usePay } from "@/hooks/usePay";
import { errorText } from "@/lib/api";
import { isOutstanding } from "@/lib/charges";
import { formatDate } from "@/lib/date";
import { formatMoney, parseAmountInput, toKobo } from "@/lib/money";

/** One charge: what it is, what's paid, what's left. Pay it in full or in part. */
export default function ChargeDetail() {
  const { t } = useTranslation();
  const { id = "" } = useLocalSearchParams<{ id: string }>();
  const charge = useCharge(id);
  const pay = usePay();
  const [partOpen, setPartOpen] = useState(false);
  const [part, setPart] = useState("");
  const [partError, setPartError] = useState<string | null>(null);

  const c = charge.data;
  const title = c ? c.description || t(`charges.kind.${c.kind}`) : t("charges.detailTitle");

  const payPart = () => {
    if (!c) return;
    const amount = parseAmountInput(part);
    const max = formatMoney(c.balance, c.currency);
    if (!amount || toKobo(amount) > toKobo(c.balance)) return setPartError(t("charges.partInvalid", { amount: max }));
    setPartError(null);
    pay.start([c.id], amount);
  };

  return (
    <Screen title={title} back onRefresh={() => charge.refetch()} refreshing={charge.isRefetching}>
      {charge.isPending && !charge.error ? (
        <SkeletonCard label={t("common.loading")} lines={5} />
      ) : !c ? (
        <Banner
          message={`${t("errors.loadFailed")} ${errorText(charge.error)}`}
          onRetry={() => charge.refetch()}
          retryLabel={t("common.retry")}
        />
      ) : (
        <View className="gap-5">
          <Card>
            <Badge status={chargeBadgeStatus(c)} />
            <Text variant="caption">{t("charges.balance")}</Text>
            <MoneyText amount={c.balance} currency={c.currency} variant="display" className={c.is_overdue ? "text-danger-700" : ""} />
            <Row label={t("charges.amount")} value={formatMoney(c.amount, c.currency)} />
            <Row label={t("charges.paid")} value={formatMoney(c.amount_paid, c.currency)} />
            <Row label={t("charges.dueDate")} value={formatDate(c.due_date)} />
            {c.period_start && c.period_end ? (
              <Row label={t("charges.period")} value={`${formatDate(c.period_start)} – ${formatDate(c.period_end)}`} />
            ) : null}
            <Row label={t("charges.property")} value={c.property_name} />
            <Row label={t("charges.unit")} value={c.unit_label} />
          </Card>

          {pay.error ? <Banner message={pay.error} /> : null}

          {isOutstanding(c) ? (
            <View className="gap-3">
              <Button
                title={t("charges.payThis", { amount: formatMoney(c.balance, c.currency) })}
                loading={pay.busy && !partOpen}
                loadingLabel={t("pay.starting")}
                disabled={pay.busy}
                onPress={() => pay.start([c.id])}
              />
              {partOpen ? (
                <Card>
                  <TextField
                    label={t("charges.partAmount")}
                    hint={t("charges.partHint", { amount: formatMoney(c.balance, c.currency) })}
                    prefix="₦"
                    keyboardType="decimal-pad"
                    value={part}
                    onChangeText={setPart}
                    error={partError ?? undefined}
                  />
                  <Button
                    title={t("charges.payNow", { amount: parseAmountInput(part) ? formatMoney(parseAmountInput(part), c.currency) : "" }).trim()}
                    loading={pay.busy}
                    loadingLabel={t("pay.starting")}
                    disabled={!part.trim()}
                    onPress={payPart}
                  />
                </Card>
              ) : (
                <Button title={t("charges.payPart")} variant="secondary" onPress={() => setPartOpen(true)} />
              )}
            </View>
          ) : null}
        </View>
      )}
    </Screen>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <View className="flex-row flex-wrap justify-between gap-2 border-t border-surface-line pt-2">
      <Text className="text-ink-600">{label}</Text>
      <Text variant="label">{value}</Text>
    </View>
  );
}
