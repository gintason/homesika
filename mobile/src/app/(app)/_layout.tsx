import { Stack } from "expo-router";

import { usePushNotifications } from "@/hooks/usePushNotifications";
import tokens from "@/theme/tokens";

export const unstable_settings = { initialRouteName: "(tabs)" };

export default function AppLayout() {
  usePushNotifications();
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
      <Stack.Screen name="bills/abroad" />
      <Stack.Screen name="bills/order/[id]" options={{ gestureEnabled: false }} />
      <Stack.Screen name="repairs/index" />
      <Stack.Screen name="repairs/new" />
      <Stack.Screen name="repairs/[id]" />
      <Stack.Screen name="work/index" />
      <Stack.Screen name="work/apply" />
      <Stack.Screen name="work/id-check" />
      <Stack.Screen name="work/address" />
      <Stack.Screen name="work/people" />
      <Stack.Screen name="work/job/[id]" />
      <Stack.Screen name="estate/index" />
      <Stack.Screen name="estate/join" />
      <Stack.Screen name="estate/pass" />
      <Stack.Screen name="alert/[id]" />
      <Stack.Screen name="invite" />
    </Stack>
  );
}
