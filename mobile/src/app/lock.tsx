import { router } from "expo-router";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Alert, Pressable, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { PinPad, Text } from "@/components";
import { errorText } from "@/lib/api";
import { formatPhone } from "@/lib/phone";
import { getSecure, setSecure } from "@/lib/secure";
import { biometricsAvailable, hasFaceUnlock } from "@/lib/security";
import { useSession } from "@/store/session";

/**
 * What a returning user sees on every launch (and after 2 minutes in the background):
 * their name and a PIN pad. Fingerprint / face if they turned it on.
 */
export default function LockScreen() {
  const { t } = useTranslation();
  const profile = useSession((s) => s.profile);
  const biometricEnabled = useSession((s) => s.biometricEnabled);
  const unlockWithPin = useSession((s) => s.unlockWithPin);
  const unlockWithBiometrics = useSession((s) => s.unlockWithBiometrics);
  const enableBiometrics = useSession((s) => s.enableBiometrics);
  const switchAccount = useSession((s) => s.switchAccount);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorSignal, setErrorSignal] = useState(0);
  const [face, setFace] = useState(false);
  const prompted = useRef(false);

  useEffect(() => {
    hasFaceUnlock().then(setFace);
    if (biometricEnabled && !prompted.current) {
      prompted.current = true;
      unlockWithBiometrics();
    }
  }, [biometricEnabled, unlockWithBiometrics]);

  /** After the first PIN unlock on a phone with fingerprint / face, offer it once. */
  const offerBiometrics = async (pin: string) => {
    if (biometricEnabled || (await getSecure("biometricAsked")) || !(await biometricsAvailable())) return;
    await setSecure("biometricAsked", "1");
    Alert.alert(t("lock.offerBioTitle"), t("lock.offerBioBody"), [
      { text: t("lock.notNow"), style: "cancel" },
      { text: t("lock.useBio"), onPress: () => enableBiometrics(pin) },
    ]);
  };

  const submit = async (pin: string) => {
    setBusy(true);
    setError(null);
    try {
      await unlockWithPin(pin);
      offerBiometrics(pin).catch(() => {});
    } catch (e) {
      setError(errorText(e));
      setErrorSignal((n) => n + 1);
      setBusy(false);
    }
  };

  const notYou = () =>
    Alert.alert(t("lock.switchTitle"), t("lock.switchBody"), [
      { text: t("common.cancel"), style: "cancel" },
      { text: t("lock.switchConfirm"), style: "destructive", onPress: switchAccount },
    ]);

  const initial = (profile?.firstName || "H")[0]?.toUpperCase();

  return (
    <SafeAreaView className="flex-1 bg-surface-background px-5">
      <View className="min-h-12 flex-row items-center justify-end">
        <Pressable onPress={notYou} accessibilityRole="button" className="min-h-12 justify-center px-2">
          <Text variant="label" className="text-primary-600">
            {t("lock.notYou")}
          </Text>
        </Pressable>
      </View>

      <View className="items-center gap-2 pt-2">
        <View className="h-16 w-16 items-center justify-center rounded-full bg-primary-800" accessibilityElementsHidden>
          <Text variant="title" className="text-white">
            {initial}
          </Text>
        </View>
        {profile?.phone ? <Text variant="caption">{formatPhone(profile.phone)}</Text> : null}
      </View>

      <View className="flex-1 justify-center">
        <PinPad
          key={errorSignal}
          title={profile?.firstName ? t("lock.welcomeBack", { name: profile.firstName }) : t("lock.title")}
          subtitle={t("lock.enterPin")}
          busy={busy}
          errorSignal={errorSignal}
          errorMessage={error ?? undefined}
          accessory={
            biometricEnabled
              ? { icon: face ? "scan-outline" : "finger-print", label: t("lock.unlock"), onPress: () => unlockWithBiometrics() }
              : undefined
          }
          onComplete={submit}
        />
      </View>

      <Pressable
        onPress={() => router.push("/forgot-pin")}
        className="min-h-12 items-center justify-center pb-4"
        accessibilityRole="button"
      >
        <Text variant="label" className="text-primary-600">
          {t("lock.forgotPin")}
        </Text>
      </Pressable>
    </SafeAreaView>
  );
}
