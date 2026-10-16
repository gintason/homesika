import { Stack } from "expo-router";

import tokens from "@/theme/tokens";

export const unstable_settings = { initialRouteName: "welcome" };

export default function AuthLayout() {
  return <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: tokens.color.surface.background } }} />;
}
