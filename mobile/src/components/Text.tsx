import { Text as RNText, type TextProps } from "react-native";

export type TextVariant = "display" | "title" | "heading" | "body" | "label" | "caption";

const VARIANTS: Record<TextVariant, string> = {
  display: "font-display text-3xl text-ink-900",
  title: "font-display text-2xl text-ink-900",
  heading: "font-display-semibold text-xl text-ink-900",
  body: "font-sans text-base text-ink-800",
  label: "font-semibold text-base text-ink-800",
  // Captions stay at 14 (secondary info only); body copy is never below 16.
  caption: "font-sans text-sm text-ink-600",
};

type Props = TextProps & { variant?: TextVariant; className?: string };

/** App text: token fonts and sizes; scales with the system font size (no fixed heights anywhere). */
export function Text({ variant = "body", className = "", ...rest }: Props) {
  return <RNText maxFontSizeMultiplier={2} {...rest} className={`${VARIANTS[variant]} ${className}`} />;
}
