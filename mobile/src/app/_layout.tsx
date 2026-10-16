import "../../global.css";
import "@/i18n";

import { Inter_400Regular, Inter_500Medium, Inter_600SemiBold } from "@expo-google-fonts/inter";
import { Montserrat_600SemiBold, Montserrat_700Bold, useFonts } from "@expo-google-fonts/montserrat";
import { QueryClientProvider } from "@tanstack/react-query";
import { Stack } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { StatusBar } from "expo-status-bar";
import { useEffect, useState } from "react";

import { useAppLock } from "@/hooks/useAppLock";
import { makeQueryClient } from "@/lib/queryClient";
import { useSession } from "@/store/session";
import tokens from "@/theme/tokens";

SplashScreen.preventAutoHideAsync().catch(() => {});

export default function RootLayout() {
  const [queryClient] = useState(makeQueryClient);
  const [fontsLoaded] = useFonts({
    Inter_400Regular,
    Inter_500Medium,
    Inter_600SemiBold,
    Montserrat_600SemiBold,
    Montserrat_700Bold,
  });
  const status = useSession((s) => s.status);
  const hydrate = useSession((s) => s.hydrate);

  useAppLock();

  useEffect(() => {
    hydrate().catch(() => useSession.setState({ status: "signedOut" }));
  }, [hydrate]);

  useEffect(() => {
    if (fontsLoaded && status !== "booting") SplashScreen.hideAsync().catch(() => {});
  }, [fontsLoaded, status]);

  // Never leave one user's cached data around for the next session.
  useEffect(() => {
    if (status === "signedOut") queryClient.clear();
  }, [status, queryClient]);

  if (!fontsLoaded || status === "booting") return null; // splash stays visible

  const background = tokens.color.surface.background;
  return (
    <QueryClientProvider client={queryClient}>
      <StatusBar style={status === "ready" ? "light" : "dark"} />
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: background } }}>
        <Stack.Protected guard={status === "ready"}>
          <Stack.Screen name="(app)" />
        </Stack.Protected>
        {/* Linked phone: the PIN screen comes first; the auth screens stay reachable for "Forgot PIN?". */}
        <Stack.Protected guard={status === "locked"}>
          <Stack.Screen name="lock" options={{ gestureEnabled: false, animation: "fade" }} />
        </Stack.Protected>
        <Stack.Protected guard={status === "signedOut" || status === "locked"}>
          <Stack.Screen name="(auth)" />
        </Stack.Protected>
      </Stack>
    </QueryClientProvider>
  );
}
