import { router } from "expo-router";
import { useTranslation } from "react-i18next";
import { View } from "react-native";

import { Banner, Button, Screen, Text } from "@/components";
import { BillCategoryTiles } from "@/components/bills";

/** Bills hub: pick a category (airtime, data, TV, electricity), or see past bill payments. */
export default function BillsHome() {
  const { t } = useTranslation();
  return (
    <Screen title={t("bills.title")} back>
      <Banner tone="info" message={t("bills.howItWorks")} />
      <View className="gap-3">
        <Text variant="heading" accessibilityRole="header">
          {t("bills.choose")}
        </Text>
        <BillCategoryTiles onPick={(category) => router.push({ pathname: "/bills/[category]", params: { category } })} />
      </View>
      <Button title={t("bills.history")} variant="secondary" onPress={() => router.push("/bills/history")} />
    </Screen>
  );
}
