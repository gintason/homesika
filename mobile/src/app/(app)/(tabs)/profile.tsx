import Constants from "expo-constants";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Alert, View } from "react-native";

import { Banner, Button, Card, Checkbox, Screen, Text } from "@/components";
import { useMe } from "@/hooks/queries";
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
