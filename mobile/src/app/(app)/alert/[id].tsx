import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Linking } from "react-native";

import { alertsApi, type DeskAlert } from "@/api";
import { Banner, Button, Card, Screen, SkeletonCard, Text } from "@/components";
import { WEB_URL } from "@/config";
import { errorText } from "@/lib/api";
import { formatDateTime } from "@/lib/date";
import { formatPhone } from "@/lib/phone";

/**
 * Opened from an alert push. Everyone it reached reports "received" (so the desk sees it got through).
 * Security staff (the push carries their organization) also see the details and can respond.
 */
export default function AlertScreen() {
  const { t } = useTranslation();
  const { id = "", org } = useLocalSearchParams<{ id: string; org?: string }>();

  useEffect(() => {
    if (id) alertsApi.received(id).catch(() => {});
  }, [id]);

  return (
    <Screen title={t("estate.alert.title")} back>
      {org ? (
        <StaffView org={org} id={id} />
      ) : (
        <Card tone="danger">
          <Text variant="label">{t("estate.alert.neighbour")}</Text>
          <Button title={t("estate.panic.call112")} variant="destructive" onPress={() => Linking.openURL("tel:112").catch(() => {})} />
        </Card>
      )}
    </Screen>
  );
}

function StaffView({ org, id }: { org: string; id: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const key = ["org", org, "alert", id];
  const q = useQuery({ queryKey: key, queryFn: () => alertsApi.desk(org, id), refetchInterval: 15_000 });
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (q.isPending) return <SkeletonCard label={t("common.loading")} />;
  if (!q.data) return <Banner message={`${t("errors.loadFailed")} ${errorText(q.error)}`} onRetry={() => q.refetch()} retryLabel={t("common.retry")} />;
  const a: DeskAlert = q.data;

  const act = async (action: "acknowledge" | "respond") => {
    setBusy(action);
    setError(null);
    try {
      qc.setQueryData(key, await alertsApi.deskAction(org, id, action));
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(null);
    }
  };

  const kind = a.kind === "drill" ? "help" : a.kind;
  return (
    <Card tone={a.status === "triggered" ? "danger" : "default"} accessibilityLiveRegion="polite">
      <Text variant="heading" accessibilityRole="header">
        {t(`estate.panic.kind.${kind}`)} · {a.estate_name}
      </Text>
      {a.house ? <Text variant="title">{t("estate.alert.house", { house: a.house })}</Text> : null}
      <Text>
        {t("estate.alert.raisedBy", { name: a.raised_by_name })} · {formatPhone(a.raised_by_phone)}
      </Text>
      <Text className="text-ink-600">{formatDateTime(a.created_at)}</Text>
      <Text variant="label">{t(`estate.panic.status.${a.status}`)}</Text>
      {a.silent ? <Text className="text-warning-700">{t("estate.panic.silentHint")}</Text> : null}
      {error ? <Banner message={error} /> : null}
      {a.location ? (
        <Button
          title={t("estate.alert.map")}
          variant="secondary"
          onPress={() => Linking.openURL(`https://www.google.com/maps?q=${a.location!.lat},${a.location!.lng}`).catch(() => {})}
        />
      ) : null}
      {a.status === "triggered" ? <Button title={t("estate.alert.acknowledge")} loading={busy === "acknowledge"} onPress={() => void act("acknowledge")} /> : null}
      {a.status === "triggered" || a.status === "acknowledged" ? (
        <Button title={t("estate.alert.respond")} variant={a.status === "triggered" ? "secondary" : "primary"} loading={busy === "respond"} onPress={() => void act("respond")} />
      ) : null}
      {WEB_URL ? (
        <Button
          title={t("estate.alert.desk")}
          variant="ghost"
          onPress={() => void WebBrowser.openBrowserAsync(`${WEB_URL}/orgs/${org}/security/${id}`).catch(() => {})}
        />
      ) : null}
    </Card>
  );
}
