import { Ionicons } from "@expo/vector-icons";
import { Pressable, View } from "react-native";

import tokens from "@/theme/tokens";

import { Text } from "./Text";

type Tone = "error" | "offline" | "info" | "success";

const TONES: Record<Tone, { box: string; text: string; icon: keyof typeof Ionicons.glyphMap; color: string }> = {
  error: { box: "bg-danger-50 border-danger-500", text: "text-danger-700", icon: "alert-circle", color: tokens.color.danger[700] },
  offline: { box: "bg-warning-50 border-warning-500", text: "text-warning-700", icon: "cloud-offline", color: tokens.color.warning[700] },
  info: { box: "bg-sky-50 border-sky-300", text: "text-primary-800", icon: "information-circle", color: tokens.color.primary[800] },
  success: { box: "bg-success-50 border-success-500", text: "text-success-700", icon: "checkmark-circle", color: tokens.color.success[700] },
};

type Props = { tone?: Tone; message: string; onRetry?: () => void; retryLabel?: string };

/** Inline message. Errors offer a retry when the caller can redo the action. */
export function Banner({ tone = "error", message, onRetry, retryLabel }: Props) {
  const s = TONES[tone];
  return (
    <View
      className={`flex-row items-center gap-3 rounded-md border px-4 py-3 ${s.box}`}
      accessibilityRole="alert"
      accessibilityLiveRegion="polite"
    >
      <Ionicons name={s.icon} size={22} color={s.color} />
      <Text className={`flex-1 ${s.text}`}>{message}</Text>
      {onRetry ? (
        <Pressable
          onPress={onRetry}
          accessibilityRole="button"
          accessibilityLabel={retryLabel}
          className="min-h-12 justify-center px-2"
        >
          <Text variant="label" className={`underline ${s.text}`}>
            {retryLabel}
          </Text>
        </Pressable>
      ) : null}
    </View>
  );
}
