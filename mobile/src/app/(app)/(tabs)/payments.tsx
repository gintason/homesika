import { useState } from "react";
import { useTranslation } from "react-i18next";
import { View } from "react-native";

import type { Payment } from "@/api";
import { Badge, Banner, Button, Card, EmptyState, MoneyText, Screen, SkeletonCard, Text } from "@/components";
import { usePayments } from "@/hooks/queries";
import { errorText } from "@/lib/api";
import { formatDateTime } from "@/lib/date";
import { downloadReceipt } from "@/lib/receipts";

/** Everything I've paid (online, or recorded by my landlord), newest first, with PDF receipts. */
export default function Payments() {
  const { t } = useTranslation();
  const q = usePayments();
  const items = q.data?.pages.flatMap((p) => p.results) ?? [];

  return (
    <Screen title={t("payments.title")} onRefresh={() => q.refetch()} refreshing={q.isRefetching && !q.isFetchingNextPage}>
      {q.isPending && !q.error ? (
        <View className="gap-4">
          <SkeletonCard label={t("common.loading")} />
          <SkeletonCard label={t("common.loading")} />
        </View>
      ) : !q.data ? (
        <Banner message={`${t("errors.loadFailed")} ${errorText(q.error)}`} onRetry={() => q.refetch()} retryLabel={t("common.retry")} />
      ) : items.length === 0 ? (
        <EmptyState icon="receipt-outline" title={t("payments.empty")} body={t("payments.emptyBody")} />
      ) : (
        <View className="gap-4">
          {q.error ? <Banner message={errorText(q.error)} onRetry={() => q.refetch()} retryLabel={t("common.retry")} /> : null}
          {items.map((p) => (
            <PaymentCard key={p.id} payment={p} />
          ))}
          {q.hasNextPage ? (
            <Button
              title={t("payments.loadMore")}
              variant="secondary"
              loading={q.isFetchingNextPage}
              onPress={() => q.fetchNextPage()}
            />
          ) : (
            <Text variant="caption" className="text-center">
              {t("payments.end")}
            </Text>
          )}
        </View>
      )}
    </Screen>
  );
}

function PaymentCard({ payment: p }: { payment: Payment }) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const items = p.applied_to.map((a) => a.description).join(", ");

  const receipt = async () => {
    if (!p.receipt_number) return;
    setBusy(true);
    setError(null);
    try {
      await downloadReceipt(p.id, p.receipt_number);
    } catch {
      setError(t("payments.receiptFailed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <View className="flex-row flex-wrap items-center justify-between gap-2">
        <MoneyText amount={p.amount} currency={p.currency} />
        <Badge
          status={p.status === "reversed" ? "void" : "paid"}
          label={p.status === "reversed" ? t("payments.reversed") : t("payments.succeeded")}
        />
      </View>
      <Text className="text-ink-600">{formatDateTime(p.paid_at)}</Text>
      {items ? <Text>{t("payments.for", { items })}</Text> : null}
      {error ? <Banner message={error} onRetry={receipt} retryLabel={t("common.retry")} /> : null}
      {p.receipt_number ? (
        <Button
          title={t("payments.getReceipt", { number: p.receipt_number })}
          variant="secondary"
          loading={busy}
          loadingLabel={t("payments.downloading")}
          onPress={receipt}
        />
      ) : (
        <Text variant="caption">{t("payments.noReceipt")}</Text>
      )}
    </Card>
  );
}
