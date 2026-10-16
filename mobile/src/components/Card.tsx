import { View, type ViewProps } from "react-native";

type Props = ViewProps & { className?: string; tone?: "default" | "navy" | "danger" };

const TONES = {
  default: "bg-surface-card border border-surface-line",
  navy: "bg-primary-800",
  danger: "bg-danger-50 border border-danger-500",
};

/** Radius 14, light border instead of heavy shadows (cheap to render on low-end Android). */
export function Card({ className = "", tone = "default", ...rest }: Props) {
  return <View className={`gap-3 rounded-lg p-4 ${TONES[tone]} ${className}`} {...rest} />;
}
