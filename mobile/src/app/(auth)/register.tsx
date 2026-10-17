import { router, useLocalSearchParams } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Pressable, View } from "react-native";

import { authApi } from "@/api";
import { Banner, Button, Checkbox, PhoneInput, Screen, Text, TextField } from "@/components";
import { PRIVACY_URL, TERMS_URL } from "@/config";
import { ApiError, errorText } from "@/lib/api";
import { isValidPhone, normalisePhone } from "@/lib/phone";
import { useAuthFlow } from "@/store/authFlow";
import { useSession } from "@/store/session";

type Field = "first_name" | "last_name" | "phone_number" | "referral_code";

/** Step 1 of sign-up. Nothing is created until the code is verified. */
export default function Register() {
  const { t } = useTranslation();
  const language = useSession((s) => s.language);
  const setChallenge = useAuthFlow((s) => s.setChallenge);
  // A shared invite link (homesika://register?code=K7PM2QX) fills in the friend's code.
  const { code = "" } = useLocalSearchParams<{ code?: string }>();
  const [form, setForm] = useState<Record<Field, string>>({
    first_name: "",
    last_name: "",
    phone_number: "",
    referral_code: String(code).toUpperCase(),
  });
  const [accepted, setAccepted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [phoneError, setPhoneError] = useState<string | null>(null);
  const set = (k: Field) => (v: string) => setForm((f) => ({ ...f, [k]: v }));
  const fieldError = (k: Field) => error?.fieldMessage(k);

  const submit = async () => {
    const phone = normalisePhone(form.phone_number);
    if (!isValidPhone(phone)) {
      setPhoneError(t("auth.phoneInvalid"));
      return;
    }
    setPhoneError(null);
    setBusy(true);
    setError(null);
    try {
      const challenge = await authApi.register({
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        phone_number: phone,
        preferred_language: language,
        accept_terms: accepted,
        ...(form.referral_code.trim() ? { referral_code: form.referral_code.trim() } : {}),
      });
      setChallenge(challenge);
      router.push("/verify");
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, "error", errorText(e)));
    } finally {
      setBusy(false);
    }
  };

  const filled = form.first_name.trim() && form.last_name.trim() && form.phone_number.trim() && accepted;
  const fieldsWithErrors = error?.code === "validation_error" ? Object.keys(error.details) : [];
  const otherError =
    error && (error.code !== "validation_error" || fieldsWithErrors.some((f) => !["first_name", "last_name", "phone_number", "referral_code"].includes(f)));

  return (
    <Screen back footer={<Button title={t("common.continue")} loading={busy} disabled={!filled} onPress={submit} />}>
      <View className="gap-1">
        <Text variant="title" accessibilityRole="header">
          {t("auth.signUpTitle")}
        </Text>
        <Text className="text-ink-600">{t("auth.signUpSubtitle")}</Text>
      </View>
      {otherError ? <Banner message={errorText(error)} /> : null}
      <TextField
        label={t("auth.firstName")}
        value={form.first_name}
        onChangeText={set("first_name")}
        autoComplete="given-name"
        textContentType="givenName"
        error={fieldError("first_name")}
      />
      <TextField
        label={t("auth.lastName")}
        value={form.last_name}
        onChangeText={set("last_name")}
        autoComplete="family-name"
        textContentType="familyName"
        error={fieldError("last_name")}
      />
      <PhoneInput
        label={t("auth.phone")}
        hint={t("auth.phoneHint")}
        placeholder="0801 234 5678"
        value={form.phone_number}
        onChangeText={set("phone_number")}
        error={phoneError ?? fieldError("phone_number")}
      />
      <TextField
        label={t("auth.referralCode")}
        hint={t("auth.referralHint")}
        value={form.referral_code}
        onChangeText={(v) => set("referral_code")(v.replace(/[^A-Za-z0-9]/g, "").toUpperCase())}
        autoCapitalize="characters"
        autoCorrect={false}
        maxLength={12}
        error={fieldError("referral_code")}
      />
      <Checkbox checked={accepted} onChange={setAccepted} label={t("auth.acceptTerms")}>
        <Text>{t("auth.acceptTerms")}</Text>
      </Checkbox>
      {TERMS_URL || PRIVACY_URL ? (
        <View className="flex-row flex-wrap gap-4">
          {TERMS_URL ? (
            <Pressable accessibilityRole="link" className="min-h-12 justify-center" onPress={() => WebBrowser.openBrowserAsync(TERMS_URL)}>
              <Text variant="label" className="text-primary-600 underline">
                {t("auth.termsLink")}
              </Text>
            </Pressable>
          ) : null}
          {PRIVACY_URL ? (
            <Pressable accessibilityRole="link" className="min-h-12 justify-center" onPress={() => WebBrowser.openBrowserAsync(PRIVACY_URL)}>
              <Text variant="label" className="text-primary-600 underline">
                {t("auth.privacyLink")}
              </Text>
            </Pressable>
          ) : null}
        </View>
      ) : null}
      <Pressable onPress={() => router.replace("/login")} accessibilityRole="link" className="min-h-12 justify-center">
        <Text variant="label" className="text-primary-600">
          {t("auth.haveAccount")}
        </Text>
      </Pressable>
    </Screen>
  );
}
