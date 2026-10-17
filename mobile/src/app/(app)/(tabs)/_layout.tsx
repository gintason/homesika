import { Ionicons } from "@expo/vector-icons";
import { Tabs } from "expo-router";
import type { ComponentProps } from "react";
import { useTranslation } from "react-i18next";

import tokens from "@/theme/tokens";

type IconName = ComponentProps<typeof Ionicons>["name"];
type IconColor = ComponentProps<typeof Ionicons>["color"];

const icon = (name: IconName) => {
  const Icon = ({ color, size }: { color: IconColor; size: number }) => <Ionicons name={name} size={size} color={color} />;
  Icon.displayName = `TabIcon(${name})`;
  return Icon;
};

export default function TabsLayout() {
  const { t } = useTranslation();
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: tokens.color.primary[600],
        tabBarInactiveTintColor: tokens.color.ink[600],
        tabBarLabelStyle: { fontFamily: "Inter_500Medium", fontSize: tokens.font.size.xs },
        tabBarStyle: { backgroundColor: tokens.color.surface.card, borderTopColor: tokens.color.surface.line, minHeight: 56 },
      }}
    >
      <Tabs.Screen name="index" options={{ title: t("tabs.home"), tabBarIcon: icon("home") }} />
      <Tabs.Screen name="charges" options={{ title: t("tabs.charges"), tabBarIcon: icon("receipt") }} />
      <Tabs.Screen name="payments" options={{ title: t("tabs.payments"), tabBarIcon: icon("card") }} />
      <Tabs.Screen name="help" options={{ title: t("tabs.help"), tabBarIcon: icon("chatbubbles") }} />
      <Tabs.Screen name="profile" options={{ title: t("tabs.profile"), tabBarIcon: icon("person-circle") }} />
    </Tabs>
  );
}
