import { Redirect, router } from "expo-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { View } from "react-native";

import { authApi } from "@/api";
import { PinPad, Screen } from "@/components";
import { ApiError, errorText } from "@/lib/api";
import { isWeakPin } from "@/lib/phone";
import { device } from "@/lib/secure";
import { useAuthFlow } from "@/store/authFlow";
import { deviceName, useSession } from "@/store/session";

/**
 * Create the 6-digit login PIN (after sign-up or a reset), then sign in on this phone.
 * No transaction PIN step: Homesika's backend doesn't require one for any tenant action.
 */
export default function CreatePin() {
  const { t } = useTranslation();
  const setupToken = useAuthFlow((s) => s.setupToken);
  const resetFlow = useAuthFlow((s) => s.reset);
  const completeSignIn = useSession((s) => s.completeSignIn);
  const [first, setFirst] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [errorSignal, setErrorSignal] = useState(0);
  const [busy, setBusy] = useState(false);

  if (!setupToken) return <Redirect href="/welcome" />;

  const restart = (message: string) => {
    setFirst(null);
    setError(message);
    setErrorSignal((n) => n + 1);
  };

  const choose = (pin: string) => {
    if (isWeakPin(pin)) return restart(t("pin.weak"));
    setError(null);
    setFirst(pin);
  };

  const confirm = async (pin: string) => {
    if (pin !== first) return restart(t("pin.mismatch"));
    setBusy(true);
    try {
      const result = await authApi.setupPin(setupToken, pin, await device.id(), deviceName());
      resetFlow();
      await completeSignIn(result);
    } catch (e) {
      const err = e instanceof ApiError ? e : null;
      if (err?.code === "setup_expired") {
        resetFlow();
        router.replace("/welcome");
        return;
      }
      restart(err?.fieldMessage("pin") ?? err?.fieldMessage("pin_confirm") ?? errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen scroll={false}>
      <View className="flex-1 justify-center">
        {first === null ? (
          <PinPad
            key={`new-${errorSignal}`}
            title={t("pin.createTitle")}
            subtitle={t("pin.createSubtitle")}
            errorSignal={errorSignal}
            errorMessage={error ?? undefined}
            onComplete={choose}
          />
        ) : (
          <PinPad key="confirm" title={t("pin.confirmTitle")} busy={busy} onComplete={confirm} />
        )}
      </View>
    </Screen>
  );
}
