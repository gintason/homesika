import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Share } from "react-native";

import { referralApi } from "@/api";
import { Banner, Button, Card, Screen, SkeletonCard, Text, TextField } from "@/components";
import { keys, useReferral } from "@/hooks/queries";
import { ApiError, errorText } from "@/lib/api";
import { copyText } from "@/lib/clipboard";
import { formatDate } from "@/lib/date";

/** My invite code, my free service fees, and "I have a friend's code" for new accounts. */
export default function Invite() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useReferral();
  const [code, setCode] = useState("");
  const [codeError, setCodeError] = useState<string | undefined>();
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (q.isPending) {
    return (
      <Screen title={t("referral.title")} back>
        <SkeletonCard label={t("common.loading")} />
      </Screen>
    );
  }
  if (!q.data) {
    return (
      <Screen title={t("referral.title")} back>
        <Banner message={`${t("errors.loadFailed")} ${errorText(q.error)}`} onRetry={() => q.refetch()} retryLabel={t("common.retry")} />
      </Screen>
    );
  }
  const r = q.data;

  const redeem = async () => {
    setBusy(true);
    setCodeError(undefined);
    try {
      qc.setQueryData(keys.referral, await referralApi.redeem(code.trim()));
      setNote(t("referral.used"));
    } catch (err) {
      setCodeError(err instanceof ApiError ? (err.fieldMessage("code") ?? errorText(err)) : errorText(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen title={t("referral.title")} back onRefresh={() => q.refetch()} refreshing={q.isRefetching}>
      {!r.enabled ? <Banner tone="info" message={t("referral.off")} /> : null}
      <Text>{t("referral.intro")}</Text>
      <Card accessible accessibilityLabel={`${t("referral.yourCode")} ${r.code.split("").join(" ")}`}>
        <Text variant="caption">{t("referral.yourCode")}</Text>
        <Text variant="display" className="tracking-widest">
          {r.code}
        </Text>
        <Text className="text-ink-600">{t("referral.stats", { invited: r.invited, qualified: r.qualified })}</Text>
      </Card>
      <Button title={t("referral.share")} onPress={() => void Share.share({ message: r.share_message }).catch(() => {})} />
      <Button
        title={t("referral.copy")}
        variant="secondary"
        onPress={async () => {
          if ((await copyText(r.code)) === "copied") setNote(t("referral.copied"));
        }}
      />
      {note ? <Banner tone="success" message={note} /> : null}
      <Card>
        <Text variant="heading">{r.waivers_available > 0 ? t("referral.free", { count: r.waivers_available }) : t("referral.freeNone")}</Text>
        {r.waivers_expire_at ? <Text className="text-ink-600">{t("referral.expires", { date: formatDate(r.waivers_expire_at) })}</Text> : null}
        <Text variant="caption" className="text-ink-600">
          {t("referral.rules")}
        </Text>
      </Card>
      {r.can_redeem ? (
        <Card>
          <Text variant="heading">{t("referral.haveCode")}</Text>
          <Text className="text-ink-600">{t("referral.haveCodeBody")}</Text>
          <TextField
            label={t("referral.enterCode")}
            value={code}
            onChangeText={(v) => setCode(v.replace(/[^A-Za-z0-9]/g, "").toUpperCase())}
            autoCapitalize="characters"
            maxLength={12}
            error={codeError}
          />
          <Button title={t("referral.use")} variant="secondary" loading={busy} disabled={code.length < 5} onPress={() => void redeem()} />
        </Card>
      ) : null}
    </Screen>
  );
}
