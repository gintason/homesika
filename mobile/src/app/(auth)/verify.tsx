import { Redirect, router } from "expo-router";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Pressable, View } from "react-native";

import { authApi, type OtpChannel } from "@/api";
import { Banner, OtpInput, Screen, Text } from "@/components";
import { ApiError, errorText } from "@/lib/api";
import { device } from "@/lib/secure";
import { useAuthFlow } from "@/store/authFlow";
import { deviceName, useSession } from "@/store/session";

/** Enter the 6-digit code sent by SMS (or email). Used by sign-up, new-phone sign-in and PIN reset. */
export default function Verify() {
  const { t } = useTranslation();
  const challenge = useAuthFlow((s) => s.challenge);
  const setChallenge = useAuthFlow((s) => s.setChallenge);
  const setSetupToken = useAuthFlow((s) => s.setSetupToken);
  const resetFlow = useAuthFlow((s) => s.reset);
  const completeSignIn = useSession((s) => s.completeSignIn);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [wait, setWait] = useState(challenge?.resend_in ?? 60);

  useEffect(() => {
    if (wait <= 0) return;
    const id = setTimeout(() => setWait((w) => w - 1), 1000);
    return () => clearTimeout(id);
  }, [wait]);

  const submit = async (value: string) => {
    if (!challenge || busy) return;
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const result = await authApi.verify(challenge.challenge_id, value, await device.id(), deviceName());
      if (result.next === "create_pin") {
        setSetupToken(result.setup_token);
        router.replace("/create-pin");
      } else {
        resetFlow();
        await completeSignIn(result); // new phone linked: straight in
      }
    } catch (e) {
      setCode("");
      setError(errorText(e));
      setBusy(false);
    }
  };

  const resend = async (channel?: OtpChannel) => {
    if (!challenge) return;
    setError(null);
    try {
      const next = await authApi.resend(challenge.challenge_id, channel);
      setChallenge(next);
      setWait(next.resend_in || 60);
      setCode("");
      setInfo(t("otp.sent"));
    } catch (e) {
      setError(e instanceof ApiError ? errorText(e) : t("errors.generic"));
    }
  };

  if (!challenge) return <Redirect href="/welcome" />;

  return (
    <Screen back>
      <View className="gap-2">
        <Text variant="title" accessibilityRole="header">
          {t("otp.title")}
        </Text>
        <Text className="text-ink-600">
          {t(challenge.channel === "sms" ? "otp.sentSms" : "otp.sentEmail", { destination: challenge.destination })}
        </Text>
      </View>
      {error ? <Banner message={error} /> : null}
      {info ? <Banner tone="success" message={info} /> : null}
      <OtpInput value={code} onChange={setCode} onComplete={submit} error={Boolean(error)} editable={!busy} />
      <View className="items-center gap-2 pt-2">
        {wait > 0 ? (
          <Text variant="caption" accessibilityLiveRegion="none">
            {t("otp.resendIn", { seconds: wait })}
          </Text>
        ) : (
          <Pressable onPress={() => resend()} accessibilityRole="button" className="min-h-12 justify-center px-2">
            <Text variant="label" className="text-primary-600">
              {t("otp.resend")}
            </Text>
          </Pressable>
        )}
        {challenge.email_fallback && wait <= 0 ? (
          <Pressable onPress={() => resend("email")} accessibilityRole="button" className="min-h-12 justify-center px-2">
            <Text variant="label" className="text-primary-600">
              {t("otp.useEmail")}
            </Text>
          </Pressable>
        ) : null}
      </View>
    </Screen>
  );
}
