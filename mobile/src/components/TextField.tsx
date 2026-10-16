import { forwardRef, useState } from "react";
import { TextInput, View, type TextInputProps } from "react-native";

import tokens from "@/theme/tokens";

import { Text } from "./Text";

export type TextFieldProps = TextInputProps & {
  label: string;
  hint?: string;
  error?: string;
  /** Rendered before the input inside the box (e.g. "+234"). */
  prefix?: string;
};

/** Labelled input with hint and error. Border ink.400 (3:1), focus primary.500, error danger.500. */
export const TextField = forwardRef<TextInput, TextFieldProps>(function TextField(
  { label, hint, error, prefix, onFocus, onBlur, ...rest },
  ref,
) {
  const [focused, setFocused] = useState(false);
  const border = error ? "border-danger-500" : focused ? "border-primary-500" : "border-ink-400";
  return (
    <View className="gap-1">
      <Text variant="label">{label}</Text>
      <View className={`min-h-12 flex-row items-center rounded-md border-2 bg-white px-3 ${border}`}>
        {prefix ? (
          <Text variant="label" className="mr-2 text-ink-600" accessibilityElementsHidden importantForAccessibility="no">
            {prefix}
          </Text>
        ) : null}
        <TextInput
          ref={ref}
          accessibilityLabel={label}
          accessibilityHint={error ?? hint}
          placeholderTextColor={tokens.color.ink[500]}
          maxFontSizeMultiplier={2}
          className="flex-1 py-3 font-sans text-base text-ink-900"
          onFocus={(e) => {
            setFocused(true);
            onFocus?.(e);
          }}
          onBlur={(e) => {
            setFocused(false);
            onBlur?.(e);
          }}
          {...rest}
        />
      </View>
      {error ? (
        <Text variant="caption" className="text-danger-700" accessibilityLiveRegion="polite" accessibilityRole="alert">
          {error}
        </Text>
      ) : hint ? (
        <Text variant="caption">{hint}</Text>
      ) : null}
    </View>
  );
});
