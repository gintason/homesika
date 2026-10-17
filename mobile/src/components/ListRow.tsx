import { Ionicons } from "@expo/vector-icons";
import type { ReactNode } from "react";
import { Pressable, View } from "react-native";

import tokens from "@/theme/tokens";

import { Text } from "./Text";

type Props = {
  title: string;
  subtitle?: string;
  /** Right-hand content (amount, badge…). */
  trailing?: ReactNode;
  /** Left-hand content (checkbox, icon…). */
  leading?: ReactNode;
  onPress?: () => void;
  accessibilityLabel?: string;
  accessibilityHint?: string;
  chevron?: boolean;
};

/** A tappable row ≥ 48 tall. Text wraps instead of truncating, so it works at 200% font size. */
export function ListRow({ title, subtitle, trailing, leading, onPress, accessibilityLabel, accessibilityHint, chevron }: Props) {
  const body = (
    <View className="min-h-12 flex-row items-center gap-3 py-3">
      {leading}
      <View className="flex-1 gap-1">
        <Text variant="label">{title}</Text>
        {subtitle ? <Text variant="caption">{subtitle}</Text> : null}
      </View>
      {trailing ? <View className="items-end gap-1">{trailing}</View> : null}
      {chevron ? <Ionicons name="chevron-forward" size={20} color={tokens.color.ink[500]} /> : null}
    </View>
  );
  // Not tappable: still read as one item ("ID check, Done") when a label is given.
  if (!onPress) return accessibilityLabel ? <View accessible accessibilityLabel={accessibilityLabel}>{body}</View> : body;
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? title}
      accessibilityHint={accessibilityHint}
      className="active:bg-surface-muted"
    >
      {body}
    </Pressable>
  );
}
