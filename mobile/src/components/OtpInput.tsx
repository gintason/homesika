import { useRef } from "react";
import { useTranslation } from "react-i18next";
import { Pressable, TextInput, View } from "react-native";

import { Text } from "./Text";

type Props = {
  value: string;
  onChange: (code: string) => void;
  /** Called once when the last digit is typed (or pasted / autofilled). */
  onComplete?: (code: string) => void;
  length?: number;
  error?: boolean;
  editable?: boolean;
  autoFocus?: boolean;
};

/**
 * One-time code boxes. A single hidden input does the typing, so iOS "From Messages" and
 * Android SMS autofill (oneTimeCode / sms-otp) can fill all six digits at once.
 */
export function OtpInput({ value, onChange, onComplete, length = 6, error, editable = true, autoFocus = true }: Props) {
  const { t } = useTranslation();
  const input = useRef<TextInput>(null);

  const change = (raw: string) => {
    const code = raw.replace(/\D/g, "").slice(0, length);
    onChange(code);
    if (code.length === length && value.length !== length) onComplete?.(code);
  };

  return (
    // The hidden TextInput is the accessible control; the wrapper only forwards taps to it.
    <Pressable onPress={() => input.current?.focus()} accessible={false}>
      <View className="flex-row justify-between gap-2" accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
        {Array.from({ length }).map((_, i) => {
          const active = i === value.length && editable;
          const border = error ? "border-danger-500" : active ? "border-primary-500" : value[i] ? "border-primary-300" : "border-ink-400";
          return (
            <View key={i} className={`min-h-12 flex-1 items-center justify-center rounded-md border-2 bg-white py-2 ${border}`}>
              <Text variant="title">{value[i] ?? ""}</Text>
            </View>
          );
        })}
      </View>
      <TextInput
        ref={input}
        testID="otp-input"
        value={value}
        onChangeText={change}
        keyboardType="number-pad"
        textContentType="oneTimeCode"
        autoComplete="sms-otp"
        maxLength={length}
        autoFocus={autoFocus}
        editable={editable}
        caretHidden
        accessibilityLabel={t("otp.codeLabel", { filled: value.length })}
        className="absolute h-full w-full opacity-0"
      />
    </Pressable>
  );
}
