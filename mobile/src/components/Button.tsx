import { ActivityIndicator, Pressable, View, type PressableProps } from "react-native";

import tokens from "@/theme/tokens";

import { Text } from "./Text";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "destructive";

const STYLES: Record<ButtonVariant, { box: string; text: string; spinner: string }> = {
  primary: { box: "bg-primary-600 active:bg-primary-700", text: "text-white", spinner: "#FFFFFF" },
  secondary: {
    box: "border-2 border-primary-600 bg-white active:bg-primary-50",
    text: "text-primary-600",
    spinner: tokens.color.primary[600],
  },
  ghost: { box: "bg-transparent active:bg-primary-50", text: "text-primary-600", spinner: tokens.color.primary[600] },
  destructive: { box: "bg-danger-500 active:bg-danger-700", text: "text-white", spinner: "#FFFFFF" },
};

type Props = Omit<PressableProps, "children"> & {
  title: string;
  variant?: ButtonVariant;
  loading?: boolean;
  /** Spoken while loading (defaults to the title). */
  loadingLabel?: string;
  className?: string;
};

/** Min 48 tall, grows with large text. Disabled while loading so money actions can't double-submit. */
export function Button({ title, variant = "primary", loading, loadingLabel, disabled, className = "", ...rest }: Props) {
  const s = STYLES[variant];
  const inactive = disabled || loading;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={loading ? (loadingLabel ?? title) : title}
      accessibilityState={{ disabled: !!inactive, busy: !!loading }}
      disabled={inactive}
      className={`min-h-12 flex-row items-center justify-center rounded-md px-5 py-3 ${s.box} ${disabled && !loading ? "opacity-50" : ""} ${className}`}
      {...rest}
    >
      <View className="flex-row items-center gap-2">
        {loading ? <ActivityIndicator color={s.spinner} testID="button-spinner" /> : null}
        <Text variant="label" className={`text-center ${s.text}`}>
          {title}
        </Text>
      </View>
    </Pressable>
  );
}
