import { Ionicons } from "@expo/vector-icons";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Pressable, View } from "react-native";
import Animated, { useAnimatedStyle, useReducedMotion, useSharedValue, withSequence, withTiming } from "react-native-reanimated";

import tokens from "@/theme/tokens";

import { Text } from "./Text";

const KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "", "0", "del"] as const;

type Accessory = { icon: keyof typeof Ionicons.glyphMap; label: string; onPress: () => void };

type Props = {
  title: string;
  subtitle?: string;
  length?: number;
  busy?: boolean;
  /** Non-zero = shake on mount. Parents remount the pad (via `key`) after a wrong PIN, which clears it. */
  errorSignal?: number;
  errorMessage?: string;
  /** Optional key in the bottom-left slot, e.g. fingerprint. */
  accessory?: Accessory;
  onComplete: (pin: string) => void;
};

/** Custom keypad with big (64pt) keys: the PIN never passes through the system keyboard. */
export function PinPad({ title, subtitle, length = 6, busy, errorSignal = 0, errorMessage, accessory, onComplete }: Props) {
  const { t } = useTranslation();
  const [pin, setPin] = useState("");
  const reduceMotion = useReducedMotion();
  const shake = useSharedValue(0);
  const shakeStyle = useAnimatedStyle(() => ({ transform: [{ translateX: shake.get() }] }));

  useEffect(() => {
    if (!errorSignal || reduceMotion) return;
    shake.set(
      withSequence(
        withTiming(-10, { duration: 50 }),
        withTiming(10, { duration: 50 }),
        withTiming(-6, { duration: 50 }),
        withTiming(0, { duration: 50 }),
      ),
    );
  }, [errorSignal, reduceMotion, shake]);

  const press = (key: (typeof KEYS)[number]) => {
    if (busy || !key) return;
    if (key === "del") return setPin((p) => p.slice(0, -1));
    setPin((p) => (p.length >= length ? p : p + key));
  };

  // Submit once the last digit lands (short delay so the final dot renders first).
  useEffect(() => {
    if (pin.length !== length) return;
    const id = setTimeout(() => onComplete(pin), 80);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fire only when the PIN changes
  }, [pin, length]);

  return (
    <View className="items-center gap-6">
      <View className="items-center gap-2">
        <Text variant="title" className="text-center" accessibilityRole="header">
          {title}
        </Text>
        {subtitle ? <Text className="text-center text-ink-600">{subtitle}</Text> : null}
      </View>

      <Animated.View style={shakeStyle} accessible accessibilityLabel={t("pin.dots", { filled: pin.length, length })}>
        <View className="flex-row gap-3">
          {Array.from({ length }).map((_, i) => (
            <View
              key={i}
              className={`h-4 w-4 rounded-full ${i < pin.length ? "bg-primary-800" : "border-2 border-ink-400 bg-white"}`}
            />
          ))}
        </View>
      </Animated.View>
      {errorMessage ? (
        <Text className="text-center text-danger-700" accessibilityRole="alert" accessibilityLiveRegion="assertive">
          {errorMessage}
        </Text>
      ) : null}

      <View className="w-full max-w-xs flex-row flex-wrap justify-between gap-y-3">
        {KEYS.map((key, i) =>
          !key && accessory ? (
            <Pressable
              key={i}
              onPress={accessory.onPress}
              disabled={busy}
              accessibilityRole="button"
              accessibilityLabel={accessory.label}
              className="h-16 w-[30%] items-center justify-center rounded-full active:bg-primary-50"
            >
              <Ionicons name={accessory.icon} size={30} color={tokens.color.primary[600]} />
            </Pressable>
          ) : (
            <Pressable
              key={i}
              onPress={() => press(key)}
              disabled={!key || busy}
              accessibilityRole={key ? "button" : undefined}
              accessibilityLabel={key === "del" ? t("pin.delete") : key || undefined}
              accessibilityElementsHidden={!key}
              importantForAccessibility={key ? "yes" : "no-hide-descendants"}
              className={`h-16 w-[30%] items-center justify-center rounded-full ${key && key !== "del" ? "bg-white active:bg-primary-50" : ""}`}
            >
              {key === "del" ? (
                <Ionicons name="backspace-outline" size={28} color={tokens.color.ink[800]} />
              ) : (
                <Text variant="title" maxFontSizeMultiplier={1.4}>
                  {key}
                </Text>
              )}
            </Pressable>
          ),
        )}
      </View>
    </View>
  );
}
