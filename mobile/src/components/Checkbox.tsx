import { Ionicons } from "@expo/vector-icons";
import type { ReactNode } from "react";
import { Pressable, View } from "react-native";

import tokens from "@/theme/tokens";

type Props = { checked: boolean; onChange: (next: boolean) => void; label: string; children?: ReactNode; disabled?: boolean };

/** 48×48 touch area around a 24 box; children render as the visible label. */
export function Checkbox({ checked, onChange, label, children, disabled }: Props) {
  return (
    <Pressable
      onPress={() => onChange(!checked)}
      disabled={disabled}
      accessibilityRole="checkbox"
      accessibilityLabel={label}
      accessibilityState={{ checked, disabled: !!disabled }}
      className="min-h-12 flex-row items-center gap-3"
    >
      <View className="h-12 w-12 items-center justify-center">
        <View
          className={`h-6 w-6 items-center justify-center rounded-sm border-2 ${checked ? "border-primary-600 bg-primary-600" : "border-ink-400 bg-white"}`}
        >
          {checked ? <Ionicons name="checkmark" size={18} color={tokens.color.ink.inverse} /> : null}
        </View>
      </View>
      {children ? <View className="flex-1">{children}</View> : null}
    </Pressable>
  );
}
