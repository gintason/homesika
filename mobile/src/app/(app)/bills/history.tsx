import { router } from "expo-router";
import { useTranslation } from "react-i18next";
import { View } from "react-native";

import type { BillOrder } from "@/api";
import { Banner, Button, EmptyState, ListRow, Screen, SkeletonCard, Text } from "@/components";
import { BillStatusBadge } from "@/components/bills";
import { useBillOrders } from "@/hooks/queries";
import { errorText } from "@/lib/api";
import { formatDateTime } from "@/lib/date";
import { formatMoney } from "@/lib/money";

/** My bill payments, newest first. Each opens the same status screen used after checkout. */
export default function BillHistory() {
  const { t } = useTranslation();
  const q = useBillOrders();
  const items = q.data?.pages.flatMap((p) => p.results) ?? [];

  return (
    <Screen title={t("bills.history")} back onRefresh={() => q.refetch()} refreshing={q.isRefetching && !q.isFetchingNextPage}>
      {q.isPending && !q.error ? (
        <View className="gap-4">
          <SkeletonCard label={t("common.loading")} />
          <SkeletonCard label={t("common.loading")} />
        </View>
      ) : !q.data ? (
        <Banner message={`${t("errors.loadFailed")} ${errorText(q.error)}`} onRetry={() => q.refetch()} retryLabel={t("common.retry")} />
      ) : items.length === 0 ? (
        <EmptyState
          icon="flash-outline"
          title={t("bills.historyEmpty")}
          body={t("bills.historyEmptyBody")}
          action={<Button title={t("bills.title")} variant="secondary" onPress={() => router.replace("/bills")} />}
        />
      ) : (
        <View className="gap-2">
          {q.error ? <Banner message={errorText(q.error)} onRetry={() => q.refetch()} retryLabel={t("common.retry")} /> : null}
          <View className="rounded-lg border border-surface-line bg-surface-card px-4">
            {items.map((o, i) => (
              <View key={o.id} className={i > 0 ? "border-t border-surface-line" : ""}>
                <OrderRow order={o} />
              </View>
            ))}
          </View>
          {q.hasNextPage ? (
            <Button title={t("bills.loadMore")} variant="secondary" loading={q.isFetchingNextPage} onPress={() => q.fetchNextPage()} />
          ) : (
            <Text variant="caption" className="text-center">
              {t("bills.end")}
            </Text>
          )}
        </View>
      )}
    </Screen>
  );
}

function OrderRow({ order: o }: { order: BillOrder }) {
  const { t } = useTranslation();
  const title = [o.biller_name, o.plan_name && o.category !== "electricity" ? o.plan_name : null].filter(Boolean).join(" · ");
  const subtitle = `${o.customer_id} · ${formatDateTime(o.created_at)}`;
  const total = formatMoney(o.total, o.currency);
  const status = t(`bills.status.${o.status}`);
  return (
    <ListRow
      title={title}
      subtitle={subtitle}
      chevron
      accessibilityLabel={`${title}, ${total}, ${status}, ${subtitle}`}
      onPress={() => router.push({ pathname: "/bills/order/[id]", params: { id: o.id } })}
      trailing={
        <>
          <Text variant="label" className="font-display">
            {total}
          </Text>
          <BillStatusBadge status={o.status} />
        </>
      }
    />
  );
}
