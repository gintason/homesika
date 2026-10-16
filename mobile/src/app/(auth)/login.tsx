import { router } from "expo-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Pressable, View } from "react-native";

import { authApi } from "@/api";
import { Button, PhoneInput, PinPad, Screen, Text } from "@/components";
import { errorText } from "@/lib/api";
import { formatPhone, isValidPhone, normalisePhone } from "@/lib/phone";
import { useAuthFlow } from "@/store/authFlow";

/** Sign in on a new (or reinstalled) phone: phone + login PIN, then a code to prove it's you. */
export default function Login() {
  const { t } = useTranslation();
  const setChallenge = useAuthFlow((s) => s.setChallenge);
  const [phone, setPhone] = useState("");
  const [phoneError, setPhoneError] = useState<string | null>(null);
  const [step, setStep] = useState<"phone" | "pin">("phone");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorSignal, setErrorSignal] = useState(0);

  const identifier = normalisePhone(phone);

  const submit = async (pin: string) => {
    setBusy(true);
    try {
      const challenge = await authApi.loginStart(identifier, pin);
      setChallenge(challenge);
      router.push("/verify");
    } catch (e) {
      setError(errorText(e));
      setErrorSignal((n) => n + 1);
    } finally {
      setBusy(false);
    }
  };

  if (step === "pin") {
    return (
      <Screen back scroll={false}>
        <View className="flex-1 justify-center gap-4">
          <PinPad
            key={errorSignal}
            title={t("pin.enterTitle")}
            subtitle={formatPhone(identifier)}
            busy={busy}
            errorSignal={errorSignal}
            errorMessage={error ?? undefined}
            onComplete={submit}
          />
          <Pressable
            onPress={() => router.push("/forgot-pin")}
            className="min-h-12 items-center justify-center"
            accessibilityRole="link"
          >
            <Text variant="label" className="text-primary-600">
              {t("lock.forgotPin")}
            </Text>
          </Pressable>
        </View>
      </Screen>
    );
  }

  return (
    <Screen
      back
      footer={
        <Button
          title={t("common.continue")}
          disabled={!phone.trim()}
          onPress={() => {
            if (!isValidPhone(identifier)) return setPhoneError(t("auth.phoneInvalid"));
            setPhoneError(null);
            setError(null);
            setStep("pin");
          }}
        />
      }
    >
      <View className="gap-1">
        <Text variant="title" accessibilityRole="header">
          {t("auth.signInTitle")}
        </Text>
        <Text className="text-ink-600">{t("auth.signInSubtitle")}</Text>
      </View>
      <PhoneInput
        label={t("auth.phone")}
        hint={t("auth.phoneHint")}
        placeholder="0801 234 5678"
        value={phone}
        onChangeText={setPhone}
        error={phoneError ?? undefined}
      />
      <Pressable onPress={() => router.replace("/register")} accessibilityRole="link" className="min-h-12 justify-center">
        <Text variant="label" className="text-primary-600">
          {t("auth.noAccount")}
        </Text>
      </Pressable>
    </Screen>
  );
}
