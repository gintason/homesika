import { useMutation, useQueryClient } from "@tanstack/react-query";
import Constants from "expo-constants";
import { router } from "expo-router";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Alert, View } from "react-native";

import { whatsappApi, type WhatsAppPref } from "@/api";
import { Banner, Button, Card, Checkbox, ListRow, Screen, Skeleton, Text } from "@/components";
import { keys, useMe, useWhatsApp } from "@/hooks/queries";
import { LANGUAGES } from "@/i18n";
import { errorText } from "@/lib/api";
import { formatPhone } from "@/lib/phone";
import { biometricsAvailable } from "@/lib/security";
import { useSession } from "@/store/session";

export default function Profile() {
  const { t } = useTranslation();
  const me = useMe();
  const profile = useSession((s) => s.profile);
  const language = useSession((s) => s.language);
  const setLanguage = useSession((s) => s.setLanguage);
  const updateProfile = useSession((s) => s.updateProfile);
  const logout = useSession((s) => s.logout);
  const biometricEnabled = useSession((s) => s.biometricEnabled);
  const disableBiometrics = useSession((s) => s.disableBiometrics);
  const [bioAvailable, setBioAvailable] = useState(false);

  useEffect(() => {
    biometricsAvailable().then(setBioAvailable);
  }, []);

  useEffect(() => {
    if (me.data) updateProfile(me.data).catch(() => {});
  }, [me.data, updateProfile]);

  const name = me.data ? `${me.data.first_name} ${me.data.last_name}`.trim() : `${profile?.firstName ?? ""} ${profile?.lastName ?? ""}`.trim();
  const phone = me.data?.phone_number ?? profile?.phone;

  const signOut = () =>
    Alert.alert(t("profile.signOutTitle"), t("profile.signOutBody"), [
      { text: t("common.cancel"), style: "cancel" },
      { text: t("profile.signOut"), style: "destructive", onPress: () => logout() },
    ]);

  return (
    <Screen title={t("profile.title")} onRefresh={() => me.refetch()} refreshing={me.isRefetching}>
      {me.error && !me.data ? <Banner message={errorText(me.error)} onRetry={() => me.refetch()} retryLabel={t("common.retry")} /> : null}
      <Card>
        <Text variant="caption">{t("profile.name")}</Text>
        <Text variant="label">{name || "—"}</Text>
        <Text variant="caption">{t("profile.phone")}</Text>
        <Text variant="label">{formatPhone(phone) || "—"}</Text>
      </Card>

      <Card>
        <Text variant="label" accessibilityRole="header">
          {t("profile.language")}
        </Text>
        <Text variant="caption">{t("profile.languageHint")}</Text>
        <View className="flex-row flex-wrap gap-3" accessibilityRole="radiogroup">
          {LANGUAGES.map((l) => (
            <Button
              key={l.code}
              title={t(`language.${l.code}`)}
              variant={language === l.code ? "primary" : "secondary"}
              accessibilityRole="radio"
              accessibilityState={{ selected: language === l.code }}
              onPress={() => setLanguage(l.code)}
              className="flex-1"
            />
          ))}
        </View>
      </Card>

      <WhatsAppCard />

      <Card>
        <ListRow title={t("profile.findPlace")} chevron onPress={() => router.push("/find")} />
      </Card>

      {/* Turning it on happens on the lock screen (it needs the PIN once); here it can be turned off. */}
      {bioAvailable && biometricEnabled ? (
        <Card>
          <Checkbox checked={biometricEnabled} onChange={() => disableBiometrics()} label={t("profile.biometrics")}>
            <Text>{t("profile.biometrics")}</Text>
          </Checkbox>
        </Card>
      ) : null}

      <Button title={t("profile.signOut")} variant="destructive" onPress={signOut} />
      <Text variant="caption" className="text-center">
        {t("profile.version", { version: Constants.expoConfig?.version ?? "" })}
      </Text>
    </Screen>
  );
}

/** GET/PUT /me/whatsapp/: reminders and receipts on WhatsApp instead of SMS. */
function WhatsAppCard() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const pref = useWhatsApp();
  const save = useMutation({
    mutationFn: whatsappApi.set,
    onSuccess: (data) => qc.setQueryData<WhatsAppPref>(keys.whatsapp, data),
  });
  const optedIn = save.isPending && save.variables !== undefined ? save.variables : (pref.data?.opted_in ?? false);

  return (
    <Card>
      <Text variant="label" accessibilityRole="header">
        {t("profile.whatsapp.title")}
      </Text>
      <Text className="text-ink-600">{t("profile.whatsapp.body")}</Text>
      {pref.isPending && !pref.error ? (
        <Skeleton className="h-12 w-full" />
      ) : pref.error && !pref.data ? (
        <Banner message={errorText(pref.error)} onRetry={() => pref.refetch()} retryLabel={t("common.retry")} />
      ) : (
        <Checkbox
          checked={optedIn}
          disabled={save.isPending}
          onChange={(next) => save.mutate(next)}
          label={t("profile.whatsapp.toggle")}
        >
          <Text>{t("profile.whatsapp.toggle")}</Text>
        </Checkbox>
      )}
      {save.error ? <Banner message={errorText(save.error)} /> : null}
      <Text variant="caption">{t("profile.whatsapp.stop")}</Text>
    </Card>
  );
}
