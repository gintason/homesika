import { router } from "expo-router";
import { useTranslation } from "react-i18next";
import { View } from "react-native";

import type { MyLease } from "@/api";
import { Badge, Banner, Button, Card, EmptyState, MoneyText, Screen, SkeletonCard, Text } from "@/components";
import { BillCategoryTiles } from "@/components/bills";
import { useLeases, useOutstandingCharges } from "@/hooks/queries";
import { usePay } from "@/hooks/usePay";
import { errorText } from "@/lib/api";
import { groupCharges, summarise } from "@/lib/charges";
import { formatDate } from "@/lib/date";
import { formatKobo } from "@/lib/money";
import { formatPhone } from "@/lib/phone";
import { useSession } from "@/store/session";

/** "My rent": what I owe, what's overdue, what's next, and one tap to pay each landlord. */
export default function Home() {
  const { t } = useTranslation();
  const profile = useSession((s) => s.profile);
  const leases = useLeases();
  const charges = useOutstandingCharges();
  const pay = usePay();

  const refreshing = leases.isRefetching || charges.isRefetching;
  const refresh = () => {
    leases.refetch();
    charges.refetch();
  };

  const loading = (leases.isPending || charges.isPending) && !(leases.error || charges.error);
  const failed = leases.error ?? charges.error;
  const hasData = leases.data !== undefined && charges.data !== undefined;

  let content: React.ReactNode;
  if (loading) {
    content = (
      <View className="gap-4">
        <SkeletonCard label={t("common.loading")} lines={4} />
        <SkeletonCard label={t("common.loading")} />
      </View>
    );
  } else if (!hasData) {
    content = <Banner message={`${t("errors.loadFailed")} ${errorText(failed)}`} onRetry={refresh} retryLabel={t("common.retry")} />;
  } else {
    const leaseList = leases.data ?? [];
    const chargeList = charges.data ?? [];
    const summary = summarise(chargeList);
    const groups = groupCharges(chargeList, leaseList);

    if (leaseList.length === 0 && chargeList.length === 0) {
      content = (
        <EmptyState
          icon="call-outline"
          title={t("home.notLinkedTitle")}
          body={t("home.notLinkedBody", { phone: formatPhone(profile?.phone) })}
          action={<Button title={t("home.findPlace")} variant="secondary" onPress={() => router.push("/find")} />}
        />
      );
    } else {
      content = (
        <View className="gap-5">
          {failed ? <Banner message={errorText(failed)} onRetry={refresh} retryLabel={t("common.retry")} /> : null}
          {chargeList.length === 0 ? (
            <EmptyState icon="checkmark-circle-outline" title={t("home.allPaid")} body={t("home.allPaidBody")} />
          ) : (
            <Card tone="navy" accessible accessibilityLabel={t("home.myRent")}>
              <Text variant="label" className="text-sky-100">
                {t("home.totalOwed")}
              </Text>
              {summary.totals.map((total) => (
                <MoneyText key={total.currency} kobo={total.totalKobo} currency={total.currency} variant="display" className="text-white" />
              ))}
              {summary.overdueCount > 0 ? (
                <View className="rounded-md bg-danger-50 px-3 py-2" testID="overdue-highlight">
                  <Text variant="label" className="text-danger-700">
                    {t("home.overdue", {
                      count: summary.overdueCount,
                      amount: summary.totals.map((x) => formatKobo(x.overdueKobo, x.currency)).join(" + "),
                    })}
                  </Text>
                </View>
              ) : null}
              {summary.nextDue ? (
                <View className="gap-1 border-t border-primary-600 pt-3">
                  <Text variant="caption" className="text-sky-100">
                    {t("home.nextDue")}
                  </Text>
                  <Text variant="label" className="text-white">
                    {summary.nextDue.description || t(`charges.kind.${summary.nextDue.kind}`)} ·{" "}
                    {t("home.dueOn", { date: formatDate(summary.nextDue.due_date) })}
                  </Text>
                </View>
              ) : null}
            </Card>
          )}

          {pay.error ? <Banner message={pay.error} /> : null}

          {groups.map((g) => (
            <Card key={g.key}>
              <View className="flex-row flex-wrap items-center justify-between gap-2">
                <Text variant="label" className="flex-1">
                  {g.landlord}
                </Text>
                {g.overdueCount > 0 ? <Badge status="overdue" /> : null}
              </View>
              <MoneyText kobo={g.totalKobo} currency={g.currency} />
              <Button
                title={groups.length > 1 ? t("home.payLandlord", { landlord: g.landlord }) : t("home.pay", { amount: formatKobo(g.totalKobo, g.currency) })}
                accessibilityHint={t("home.pay", { amount: formatKobo(g.totalKobo, g.currency) })}
                loading={pay.busy}
                loadingLabel={t("pay.starting")}
                onPress={() => pay.start(g.charges.map((c) => c.id))}
              />
              <Button
                title={t("charges.title")}
                variant="ghost"
                onPress={() => router.push({ pathname: "/charges", params: { group: g.key } })}
              />
            </Card>
          ))}

          {leaseList.map((lease) => (
            <LeaseCard key={lease.id} lease={lease} />
          ))}

          <Button title={t("home.seePayments")} variant="secondary" onPress={() => router.push("/payments")} />
          <Button title={t("home.findPlace")} variant="ghost" onPress={() => router.push("/find")} />
        </View>
      );
    }
  }

  return (
    <Screen
      title={profile?.firstName ? t("home.greeting", { name: profile.firstName }) : t("home.myRent")}
      onRefresh={refresh}
      refreshing={refreshing}
    >
      {content}
      <BillsCard />
    </Screen>
  );
}

function LeaseCard({ lease }: { lease: MyLease }) {
  const { t } = useTranslation();
  return (
    <Card>
      <Text variant="caption">{t("home.myHome")}</Text>
      <Text variant="label">
        {lease.property_name} · {lease.unit_label}
      </Text>
      {lease.property_address ? <Text className="text-ink-600">{lease.property_address}</Text> : null}
      <Text className="text-ink-600">{t("home.landlordLine", { name: lease.landlord })}</Text>
    </Card>
  );
}

/** Bills entry (the tab bar is full): airtime, data, TV and electricity, one tap each. */
function BillsCard() {
  const { t } = useTranslation();
  return (
    <Card accessibilityLabel={t("bills.title")}>
      <Text variant="heading" accessibilityRole="header">
        {t("bills.title")}
      </Text>
      <Text className="text-ink-600">{t("bills.homeBody")}</Text>
      <BillCategoryTiles compact onPick={(category) => router.push({ pathname: "/bills/[category]", params: { category } })} />
      <Button title={t("bills.history")} variant="ghost" onPress={() => router.push("/bills/history")} />
    </Card>
  );
}
