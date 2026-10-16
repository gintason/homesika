import { Image } from "expo-image";
import { router } from "expo-router";
import { useTranslation } from "react-i18next";
import { View } from "react-native";

import { Button, Screen, Text } from "@/components";
import { LANGUAGES } from "@/i18n";
import { useSession } from "@/store/session";

const logo = require("../../../assets/homesika-logo.jpg");

export default function Welcome() {
  const { t } = useTranslation();
  const language = useSession((s) => s.language);
  const setLanguage = useSession((s) => s.setLanguage);

  return (
    <Screen
      footer={
        <View className="gap-3">
          <Button title={t("welcome.getStarted")} onPress={() => router.push("/register")} />
          <Button title={t("welcome.haveAccount")} variant="secondary" onPress={() => router.push("/login")} />
        </View>
      }
    >
      <View className="flex-1 items-center justify-center gap-6">
        <Image source={logo} style={{ width: 220, height: 120 }} contentFit="contain" accessibilityLabel="Homesika" />
        <Text variant="title" className="text-center text-primary-800" accessibilityRole="header">
          {t("welcome.title")}
        </Text>
        <Text className="text-center text-ink-600">{t("welcome.subtitle")}</Text>
        <View className="flex-row gap-2" accessibilityRole="radiogroup">
          {LANGUAGES.map((l) => (
            <Button
              key={l.code}
              title={t(`language.${l.code}`)}
              variant={language === l.code ? "primary" : "ghost"}
              accessibilityRole="radio"
              accessibilityState={{ selected: language === l.code }}
              onPress={() => setLanguage(l.code)}
            />
          ))}
        </View>
      </View>
    </Screen>
  );
}
