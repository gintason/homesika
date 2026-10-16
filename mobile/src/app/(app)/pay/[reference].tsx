import { Ionicons } from "@expo/vector-icons";
import { router, useLocalSearchParams } from "expo-router";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { ActivityIndicator, View } from "react-native";

import { Button, Screen, Text } from "@/components";
import { useInvalidateMoney } from "@/hooks/queries";
import { usePayStatus } from "@/hooks/usePayStatus";
import { useSession } from "@/store/session";
import tokens from "@/theme/tokens";

/** After checkout: poll the status and say clearly whether the money arrived. */
export default function PayResult() {
  const { t } = useTranslation();
  const { reference = "" } = useLocalSearchParams<{ reference: string }>();
  const { phase, linkStatus, receiptNumber, checkAgain } = usePayStatus(reference);
  const invalidate = useInvalidateMoney();
  const resumeLock = useSession((s) => s.resumeLock);

  useEffect(() => {
    if (phase === "paid" || phase === "failed") {
      resumeLock();
      invalidate().catch(() => {});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per final phase
  }, [phase]);

  useEffect(() => () => resumeLock(), [resumeLock]);

  const done = () => router.replace("/");

  let icon: keyof typeof Ionicons.glyphMap = "time-outline";
  let color: string = tokens.color.warning[700];
  let title = t("pay.processingTitle");
  let body = t("pay.processingBody");
  if (phase === "checking") {
    title = t("pay.checkingTitle");
    body = t("pay.checkingBody");
  } else if (phase === "paid") {
    icon = "checkmark-circle";
    color = tokens.color.success[500];
    title = t("pay.successTitle");
    body = t("pay.successBody");
  } else if (phase === "failed") {
    icon = "close-circle";
    color = tokens.color.danger[500];
    title = t("pay.notPaidTitle");
    body = t("pay.notPaidBody", {
      status: t(linkStatus === "cancelled" ? "pay.status.cancelled" : "pay.status.expired"),
    });
  }

  return (
    <Screen
      footer={
        <View className="gap-3">
          {phase === "processing" ? <Button title={t("pay.checkAgain")} onPress={checkAgain} /> : null}
          {phase === "paid" ? <Button title={t("pay.viewPayments")} onPress={() => router.replace("/payments")} /> : null}
          <Button
            title={t("pay.backHome")}
            variant={phase === "paid" || phase === "processing" ? "secondary" : "primary"}
            onPress={done}
          />
        </View>
      }
    >
      <View className="flex-1 items-center justify-center gap-4" accessibilityLiveRegion="polite">
        {phase === "checking" ? (
          <ActivityIndicator size="large" color={tokens.color.primary[600]} accessibilityLabel={title} />
        ) : (
          <Ionicons name={icon} size={72} color={color} accessibilityElementsHidden />
        )}
        <Text variant="title" className="text-center" accessibilityRole="header">
          {title}
        </Text>
        <Text className="text-center text-ink-600">{body}</Text>
        {phase === "paid" && receiptNumber ? (
          <Text variant="label" className="text-center">
            {t("pay.receiptNumber", { number: receiptNumber })}
          </Text>
        ) : null}
      </View>
    </Screen>
  );
}
