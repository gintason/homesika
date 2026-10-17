import { Stack } from "expo-router";

import tokens from "@/theme/tokens";

export const unstable_settings = { initialRouteName: "(tabs)" };

export default function AppLayout() {
  return (
    <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: tokens.color.surface.background } }}>
      <Stack.Screen name="(tabs)" />
      <Stack.Screen name="charge/[id]" />
      <Stack.Screen name="pay/[reference]" options={{ gestureEnabled: false }} />
      <Stack.Screen name="find/index" />
      <Stack.Screen name="find/[ref]" />
      <Stack.Screen name="bills/index" />
      <Stack.Screen name="bills/[category]" />
      <Stack.Screen name="bills/history" />
      <Stack.Screen name="bills/order/[id]" options={{ gestureEnabled: false }} />
    </Stack>
  );
}
