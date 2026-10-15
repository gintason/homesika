import { Image } from "expo-image";
import { Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

const logo = require("../../assets/homesika-logo.jpg");

/** Phase 0 shell: brand and tokens wired up. Onboarding and tenant screens arrive in Phase 1. */
export default function Home() {
  return (
    <SafeAreaView className="flex-1 bg-surface-background">
      <View className="flex-1 items-center justify-center gap-6 px-5">
        <Image source={logo} style={{ width: 220, height: 120 }} contentFit="contain" accessibilityLabel="Homesika" />
        <Text className="text-center font-display text-2xl text-ink-900">Homesika</Text>
        <Text className="text-center font-sans text-base text-ink-600">
          Rent, bills, repairs and estate security in one app.
        </Text>
        <View className="rounded-pill bg-primary-50 px-4 py-2">
          <Text className="font-semibold text-sm text-primary-600">Phase 0 · foundations</Text>
        </View>
      </View>
    </SafeAreaView>
  );
}
