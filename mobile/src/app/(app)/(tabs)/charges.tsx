import { router, useLocalSearchParams } from "expo-router";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { View } from "react-native";

import {
  Badge,
  Banner,
  Button,
  Card,
  chargeBadgeStatus,
  Checkbox,
  EmptyState,
  ListRow,
  MoneyText,
  Screen,
  SkeletonCard,
  Text,
} from "@/components";
import { useLeases, useOutstandingCharges } from "@/hooks/queries";
import { usePay } from "@/hooks/usePay";
import { errorText } from "@/lib/api";
import { groupCharges } from "@/lib/charges";
import { formatDate } from "@/lib/date";
import { formatKobo, sumKobo } from "@/lib/money";

type Selection = { group: string; ids: string[] };

/**
 * Unpaid charges grouped by landlord. You can select charges from ONE landlord at a time
 * (the API rejects mixing); picking from another landlord switches the selection.
 */
export default function Charges() {
  const { t } = useTranslation();
  const params = useLocalSearchParams<{ group?: string }>();
  const leases = useLeases();
  const charges = useOutstandingCharges();
  const pay = usePay();
  /** undefined = the user hasn't picked anything yet (use the ?group= preselection from Home). */
  const [picked, setPicked] = useState<Selection | null | undefined>(undefined);
  const [notice, setNotice] = useState<string | null>(null);

  const groups = useMemo(
    () => (charges.data && leases.data ? groupCharges(charges.data, leases.data) : []),
    [charges.data, leases.data],
  );

  // Derived, not synced: drop anything no longer outstanding (e.g. after paying).
  const selected = useMemo<Selection | null>(() => {
    const base =
      picked !== undefined
        ? picked
        : (() => {
            const g = groups.find((x) => x.key === params.group);
            return g ? { group: g.key, ids: g.charges.map((c) => c.id) } : null;
          })();
    if (!base) return null;
    const g = groups.find((x) => x.key === base.group);
    const ids = base.ids.filter((id) => g?.charges.some((c) => c.id === id));
    return ids.length ? { group: base.group, ids } : null;
  }, [picked, groups, params.group]);

  const toggle = (groupKey: string, id: string, landlord: string) => {
    setNotice(null);
    if (!selected || selected.group !== groupKey) {
      if (selected?.ids.length) setNotice(t("charges.oneLandlord", { landlord }));
      setPicked({ group: groupKey, ids: [id] });
      return;
    }
    const ids = selected.ids.includes(id) ? selected.ids.filter((x) => x !== id) : [...selected.ids, id];
    setPicked(ids.length ? { group: groupKey, ids } : null);
  };

  const selGroup = selected ? groups.find((g) => g.key === selected.group) : undefined;
  const selCharges = selGroup?.charges.filter((c) => selected?.ids.includes(c.id)) ?? [];
  const selKobo = sumKobo(selCharges.map((c) => c.balance));
  const selAmount = formatKobo(selKobo, selGroup?.currency);

  const refresh = () => {
    leases.refetch();
    charges.refetch();
  };
  const failed = charges.error ?? leases.error;
  const loading = (charges.isPending || leases.isPending) && !failed;

  return (
    <Screen
      title={t("charges.title")}
      onRefresh={refresh}
      refreshing={charges.isRefetching || leases.isRefetching}
      footer={
        selCharges.length ? (
          <View className="gap-2">
            <Text className="text-center text-ink-600">{t("charges.selected", { count: selCharges.length, amount: selAmount })}</Text>
            <Button
              title={t("charges.payNow", { amount: selAmount })}
              loading={pay.busy}
              loadingLabel={t("pay.starting")}
              onPress={() => pay.start(selCharges.map((c) => c.id))}
            />
          </View>
        ) : undefined
      }
    >
      {loading ? (
        <View className="gap-4">
          <SkeletonCard label={t("common.loading")} />
          <SkeletonCard label={t("common.loading")} />
        </View>
      ) : !charges.data || !leases.data ? (
        <Banner message={`${t("errors.loadFailed")} ${errorText(failed)}`} onRetry={refresh} retryLabel={t("common.retry")} />
      ) : groups.length === 0 ? (
        <EmptyState icon="checkmark-circle-outline" title={t("charges.empty")} body={t("charges.emptyBody")} />
      ) : (
        <View className="gap-5">
          {failed ? <Banner message={errorText(failed)} onRetry={refresh} retryLabel={t("common.retry")} /> : null}
          {notice ? <Banner tone="info" message={notice} /> : null}
          {pay.error ? <Banner message={pay.error} /> : null}
          {groups.map((g) => (
            <Card key={g.key}>
              <View className="gap-1">
                <Text variant="heading">{g.landlord}</Text>
                <Text className="text-ink-600">{t("charges.groupTotal", { amount: formatKobo(g.totalKobo, g.currency) })}</Text>
              </View>
              {g.charges.map((c) => {
                const name = c.description || t(`charges.kind.${c.kind}`);
                const checked = selected?.group === g.key && selected.ids.includes(c.id);
                return (
                  <View key={c.id} className="flex-row items-center border-t border-surface-line">
                    <Checkbox
                      checked={checked}
                      onChange={() => toggle(g.key, c.id, g.landlord)}
                      label={t("charges.select", { name: `${name}, ${formatKobo(sumKobo([c.balance]), c.currency)}` })}
                    />
                    <View className="flex-1">
                      <ListRow
                        title={name}
                        subtitle={`${c.property_name} · ${c.unit_label} · ${t("charges.due", { date: formatDate(c.due_date) })}`}
                        trailing={
                          <>
                            <MoneyText amount={c.balance} currency={c.currency} variant="label" />
                            <Badge status={chargeBadgeStatus(c)} />
                          </>
                        }
                        chevron
                        onPress={() => router.push({ pathname: "/charge/[id]", params: { id: c.id } })}
                      />
                    </View>
                  </View>
                );
              })}
            </Card>
          ))}
        </View>
      )}
    </Screen>
  );
}
