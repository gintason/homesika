import { Ionicons } from "@expo/vector-icons";
import type { ReactNode } from "react";
import { View } from "react-native";

import tokens from "@/theme/tokens";

import { Text } from "./Text";

type Props = { icon?: keyof typeof Ionicons.glyphMap; title: string; body?: string; action?: ReactNode };

export function EmptyState({ icon = "home-outline", title, body, action }: Props) {
  return (
    <View className="items-center gap-3 px-4 py-10" accessible accessibilityRole="summary">
      <View className="h-16 w-16 items-center justify-center rounded-full bg-sky-50">
        <Ionicons name={icon} size={32} color={tokens.color.primary[600]} />
      </View>
      <Text variant="heading" className="text-center">
        {title}
      </Text>
      {body ? <Text className="text-center text-ink-600">{body}</Text> : null}
      {action}
    </View>
  );
}
