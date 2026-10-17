import { router } from "expo-router";
import { useTranslation } from "react-i18next";
import { View } from "react-native";

import type { Ticket } from "@/api";
import { Banner, Button, EmptyState, ListRow, Screen, SkeletonCard, Text } from "@/components";
import { PriorityBadge, TicketStatusBadge } from "@/components/repairs";
import { useLeases, useTickets } from "@/hooks/queries";
import { errorText } from "@/lib/api";
import { formatDate } from "@/lib/date";

/** My repair requests, newest first, with "Report a problem" for tenants with an active lease. */
export default function RepairsHome() {
  const { t } = useTranslation();
  const q = useTickets();
  const leases = useLeases();
  const canReport = (leases.data ?? []).some((l) => l.status === "active");
  const items = q.data?.pages.flatMap((p) => p.results) ?? [];

  return (
    <Screen
      title={t("repairs.title")}
      back
      onRefresh={() => q.refetch()}
      refreshing={q.isRefetching && !q.isFetchingNextPage}
      footer={canReport ? <Button title={t("repairs.report")} onPress={() => router.push("/repairs/new")} /> : undefined}
    >
      {leases.data && !canReport ? <Banner tone="info" message={t("repairs.noLease")} /> : null}
      {q.isPending && !q.error ? (
        <View className="gap-4">
          <SkeletonCard label={t("common.loading")} />
          <SkeletonCard label={t("common.loading")} />
        </View>
      ) : !q.data ? (
        <Banner message={`${t("errors.loadFailed")} ${errorText(q.error)}`} onRetry={() => q.refetch()} retryLabel={t("common.retry")} />
      ) : items.length === 0 ? (
        <EmptyState icon="construct-outline" title={t("repairs.empty")} body={t("repairs.emptyBody")} />
      ) : (
        <View className="gap-2">
          <Text variant="heading" accessibilityRole="header">
            {t("repairs.myRequests")}
          </Text>
          <View className="rounded-lg border border-surface-line bg-surface-card px-4">
            {items.map((ticket, i) => (
              <View key={ticket.id} className={i > 0 ? "border-t border-surface-line" : ""}>
                <TicketRow ticket={ticket} />
              </View>
            ))}
          </View>
          {q.hasNextPage ? (
            <Button title={t("bills.loadMore")} variant="secondary" loading={q.isFetchingNextPage} onPress={() => q.fetchNextPage()} />
          ) : null}
        </View>
      )}
    </Screen>
  );
}

function TicketRow({ ticket }: { ticket: Ticket }) {
  const { t } = useTranslation();
  const subtitle = `${ticket.unit.label} · ${formatDate(ticket.created_at)}`;
  const status = t(`repairs.status.${ticket.status}`);
  return (
    <ListRow
      title={ticket.title}
      subtitle={subtitle}
      chevron
      accessibilityLabel={`${ticket.title}, ${status}, ${subtitle}`}
      onPress={() => router.push({ pathname: "/repairs/[id]", params: { id: ticket.id } })}
      trailing={
        <>
          <TicketStatusBadge status={ticket.status} />
          <PriorityBadge priority={ticket.priority} />
        </>
      }
    />
  );
}
