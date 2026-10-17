import { useQueryClient } from "@tanstack/react-query";
import { router } from "expo-router";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Alert, Linking, View } from "react-native";

import { alertsApi, estatesApi, type GatePass, type MyAlert, type MyEstate, type PanicKind, type TriggerInput } from "@/api";
import { Banner, Button, Card, EmptyState, MoneyText, Screen, SkeletonCard, Text } from "@/components";
import { KindChips, PanicButton, ToggleRow } from "@/components/estate";
import { keys, useAnnouncements, useMyAlerts, useMyEstates, usePasses } from "@/hooks/queries";
import { errorText } from "@/lib/api";
import { formatDate, formatDateTime } from "@/lib/date";
import { toKobo } from "@/lib/money";
import { currentLocation, isOpen, newClientId, sendAlert } from "@/lib/panic";
import { getSecure, setSecure } from "@/lib/secure";

/** My estate: the panic button first, then gate passes, news and dues. */
export default function EstateHome() {
  const { t } = useTranslation();
  const estates = useMyEstates();
  const list = estates.data ?? [];
  const member = list.find((m) => m.status === "approved") ?? list[0];

  let content: React.ReactNode;
  if (estates.isPending) content = <SkeletonCard label={t("common.loading")} lines={4} />;
  else if (estates.error && !estates.data)
    content = <Banner message={`${t("errors.loadFailed")} ${errorText(estates.error)}`} onRetry={() => estates.refetch()} retryLabel={t("common.retry")} />;
  else if (!member)
    content = (
      <EmptyState
        icon="shield-checkmark-outline"
        title={t("estate.joinTitle")}
        body={t("estate.homeJoinBody")}
        action={<Button title={t("estate.join")} onPress={() => router.push("/estate/join")} />}
      />
    );
  else if (member.status === "pending")
    content = (
      <Card>
        <Text variant="heading" accessibilityRole="header">
          {t("estate.pendingTitle")}
        </Text>
        <Text className="text-ink-600">{t("estate.pendingBody", { estate: member.estate_name, house: member.house })}</Text>
      </Card>
    );
  else if (member.status !== "approved") content = <Banner message={t("estate.suspended", { estate: member.estate_name })} />;
  else content = <Member member={member} />;

  return (
    <Screen title={member?.estate_name ?? t("estate.title")} back onRefresh={() => estates.refetch()} refreshing={estates.isRefetching}>
      {content}
    </Screen>
  );
}

function Member({ member }: { member: MyEstate }) {
  const { t } = useTranslation();
  const passes = usePasses();
  const news = useAnnouncements(member.estate_id);
  const owed = toKobo(member.dues_outstanding);
  return (
    <View className="gap-5">
      <PanicSection member={member} />
      {owed > 0 ? (
        <Card accessibilityLabel={t("estate.duesOwed")}>
          <Text variant="caption">{t("estate.duesOwed")}</Text>
          <MoneyText kobo={owed} currency="NGN" />
          <Button title={t("estate.payDues")} variant="secondary" onPress={() => router.push("/charges")} />
        </Card>
      ) : null}
      <Card>
        <Text variant="heading" accessibilityRole="header">
          {t("estate.passes.title")}
        </Text>
        {(passes.data ?? []).filter((p) => p.estate === member.estate_id).length === 0 ? (
          <Text className="text-ink-600">{t("estate.passes.emptyBody")}</Text>
        ) : (
          (passes.data ?? []).filter((p) => p.estate === member.estate_id).map((p) => <PassRow key={p.id} pass={p} />)
        )}
        <Button title={t("estate.passes.new")} onPress={() => router.push({ pathname: "/estate/pass", params: { estate: member.estate_id } })} />
      </Card>
      <Card>
        <Text variant="heading" accessibilityRole="header">
          {t("estate.news.title")}
        </Text>
        {(news.data ?? []).length === 0 ? <Text className="text-ink-600">{t("estate.news.empty")}</Text> : null}
        {(news.data ?? []).slice(0, 5).map((a) => (
          <View key={a.id} className="gap-1 border-t border-surface-line pt-3">
            <Text variant="label">{a.title}</Text>
            <Text>{a.body}</Text>
            <Text variant="caption" className="text-ink-600">
              {formatDate(a.created_at)}
            </Text>
          </View>
        ))}
      </Card>
    </View>
  );
}

function PassRow({ pass }: { pass: GatePass }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const cancel = async () => {
    setBusy(true);
    try {
      await estatesApi.cancelPass(pass.id);
      await qc.invalidateQueries({ queryKey: keys.passes });
    } finally {
      setBusy(false);
    }
  };
  return (
    <View className="gap-1 border-t border-surface-line pt-3" accessible accessibilityLabel={`${pass.visitor_name}, ${t("estate.passes.code")} ${pass.code.split("").join(" ")}`}>
      <Text variant="label">
        {pass.visitor_name} · {t(`estate.passes.kinds.${pass.kind}`)}
      </Text>
      <Text variant="title" className="tracking-widest">
        {pass.code}
      </Text>
      <Text variant="caption" className="text-ink-600">
        {t("estate.passes.until", { time: formatDateTime(pass.valid_to) })} · {t("estate.passes.uses", { uses: pass.uses, max: pass.max_uses })}
      </Text>
      <Button title={t("estate.passes.cancel")} variant="ghost" loading={busy} onPress={() => void cancel()} />
    </View>
  );
}

const call112 = () => Linking.openURL("tel:112").catch(() => {});

function PanicSection({ member }: { member: MyEstate }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const alerts = useMyAlerts();
  const [silent, setSilent] = useState(false);
  const [shareLocation, setShareLocation] = useState(false);
  const [sending, setSending] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const [sent, setSent] = useState<MyAlert | null>(null);
  const clientId = useRef<string | null>(null);
  const location = useRef<Promise<TriggerInput["location"]> | null>(null);

  useEffect(() => {
    getSecure("panicLocation")
      .then((v) => setShareLocation(v === "1"))
      .catch(() => {});
  }, []);

  const open = sent && isOpen(sent) ? sent : (alerts.data ?? []).find((a) => a.estate === member.estate_id && isOpen(a));

  if (!member.panic_enabled) {
    return (
      <Card>
        <Banner tone="info" message={t("estate.panic.off")} />
        <Button title={t("estate.panic.call112")} variant="destructive" onPress={call112} />
      </Card>
    );
  }

  const holdStart = () => {
    clientId.current = clientId.current ?? newClientId(); // same id for every retry of this alert
    location.current = shareLocation ? currentLocation() : Promise.resolve(null);
  };

  const trigger = async () => {
    if (sending) return;
    setSending(true);
    setFailed(null);
    try {
      // Wait a moment for the location, but never long: the alert matters more.
      const loc = await Promise.race([location.current ?? Promise.resolve(null), new Promise<null>((r) => setTimeout(() => r(null), 1500))]);
      const alert = await sendAlert({ estate: member.estate_id, kind: "help", silent, client_id: clientId.current ?? newClientId(), location: loc });
      setSent(alert);
      clientId.current = null;
      await qc.invalidateQueries({ queryKey: keys.alerts });
    } catch (err) {
      setFailed(errorText(err));
    } finally {
      setSending(false);
    }
  };

  const setKind = async (kind: PanicKind) => {
    if (!open) return;
    try {
      setSent(await alertsApi.setKind(open.id, kind));
    } catch {
      // the alert is already out; the kind is extra detail
    }
  };

  const imSafe = () =>
    open &&
    Alert.alert(t("estate.panic.cancelTitle"), t("estate.panic.cancelBody"), [
      { text: t("common.cancel"), style: "cancel" },
      {
        text: t("estate.panic.imSafe"),
        onPress: async () => {
          try {
            setSent(await alertsApi.cancel(open.id));
            await qc.invalidateQueries({ queryKey: keys.alerts });
          } catch (err) {
            setFailed(errorText(err));
          }
        },
      },
    ]);

  if (open) {
    return (
      <Card tone="danger" accessibilityLiveRegion="polite">
        <Text variant="heading" accessibilityRole="header">
          {open.silent ? t("estate.panic.sentSilent") : t("estate.panic.sent")}
        </Text>
        <Text variant="label">{t(`estate.panic.status.${open.status}`)}</Text>
        <Text variant="label">{t("estate.panic.whatsHappening")}</Text>
        <KindChips value={open.kind} onPick={(k) => void setKind(k)} />
        <Button title={t("estate.panic.call112")} variant="destructive" onPress={call112} />
        <Button title={t("estate.panic.imSafe")} variant="secondary" onPress={imSafe} />
      </Card>
    );
  }

  return (
    <Card>
      <Text variant="heading" accessibilityRole="header">
        {t("estate.panic.title")}
      </Text>
      <PanicButton onHoldStart={holdStart} onTrigger={() => void trigger()} disabled={sending} quiet={silent} />
      {sending ? <Banner tone="info" message={t("estate.panic.sending")} /> : null}
      {failed ? (
        <View className="gap-2" accessibilityLiveRegion="assertive">
          <Banner message={`${t("estate.panic.failed")} ${failed}`} onRetry={() => void trigger()} retryLabel={t("common.retry")} />
        </View>
      ) : null}
      <ToggleRow label={t("estate.panic.silent")} hint={t("estate.panic.silentHint")} value={silent} onChange={setSilent} />
      <ToggleRow
        label={t("estate.panic.location")}
        hint={t("estate.panic.locationHint")}
        value={shareLocation}
        onChange={(v) => {
          setShareLocation(v);
          setSecure("panicLocation", v ? "1" : "0").catch(() => {});
        }}
      />
      <Button title={t("estate.panic.call112")} variant="destructive" onPress={call112} />
    </Card>
  );
}
