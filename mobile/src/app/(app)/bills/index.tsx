import { router } from "expo-router";
import { useTranslation } from "react-i18next";
import { View } from "react-native";

import { Banner, Button, Card, Screen, Text } from "@/components";
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
      <Card accessibilityLabel={t("bills.intl.tile")}>
        <Text variant="heading">{t("bills.intl.tile")}</Text>
        <Text className="text-ink-600">{t("bills.intl.tileBody")}</Text>
        <Button title={t("bills.intl.tile")} variant="secondary" onPress={() => router.push("/bills/abroad")} />
      </Card>
      <Button title={t("bills.history")} variant="secondary" onPress={() => router.push("/bills/history")} />
    </Screen>
  );
}
