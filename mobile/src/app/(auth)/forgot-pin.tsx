import { router } from "expo-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { View } from "react-native";

import { authApi } from "@/api";
import { Banner, Button, PhoneInput, Screen, Text } from "@/components";
import { errorText } from "@/lib/api";
import { isValidPhone, normalisePhone } from "@/lib/phone";
import { useAuthFlow } from "@/store/authFlow";
import { useSession } from "@/store/session";

/** Reset the login PIN with a code. Every other phone gets signed out. */
export default function ForgotPin() {
  const { t } = useTranslation();
  const setChallenge = useAuthFlow((s) => s.setChallenge);
  const knownPhone = useSession((s) => s.profile?.phone ?? "");
  const [phone, setPhone] = useState(knownPhone);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    const id = normalisePhone(phone);
    if (!isValidPhone(id)) return setError(t("auth.phoneInvalid"));
    setBusy(true);
    setError(null);
    try {
      setChallenge(await authApi.forgotPin(id));
      router.push("/verify");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen back footer={<Button title={t("otp.sendCode")} loading={busy} disabled={!phone.trim()} onPress={submit} />}>
      <View className="gap-1">
        <Text variant="title" accessibilityRole="header">
          {t("pin.forgotTitle")}
        </Text>
        <Text className="text-ink-600">{t("pin.forgotSubtitle")}</Text>
      </View>
      {error ? <Banner message={error} /> : null}
      <PhoneInput label={t("auth.phone")} hint={t("auth.phoneHint")} value={phone} onChangeText={setPhone} autoFocus />
    </Screen>
  );
}
