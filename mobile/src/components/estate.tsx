import * as Haptics from "expo-haptics";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Alert, Animated, Easing, Pressable, Switch, View } from "react-native";

import { PANIC_KINDS, type PanicKind } from "@/api";
import { HOLD_MS } from "@/lib/panic";
import tokens from "@/theme/tokens";

import { Text } from "./Text";

const haptic = (style: Haptics.ImpactFeedbackStyle) => Haptics.impactAsync(style).catch(() => {});

/**
 * The panic button: hold for HOLD_MS to send. Emergency red is used ONLY here. A ring fills while
 * held; letting go early cancels. Screen-reader users double tap and confirm instead (holding is
 * hard with VoiceOver/TalkBack).
 */
export function PanicButton({
  onTrigger,
  onHoldStart,
  disabled,
  quiet,
}: {
  onTrigger: () => void;
  /** Called as the hold begins (e.g. start finding the location so the alert isn't delayed). */
  onHoldStart?: () => void;
  disabled?: boolean;
  /** Silent alert: no vibration when it sends. */
  quiet?: boolean;
}) {
  const { t } = useTranslation();
  const [progress] = useState(() => new Animated.Value(0));
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [holding, setHolding] = useState(false);

  useEffect(() => () => void (timer.current && clearTimeout(timer.current)), []);

  const start = () => {
    if (disabled) return;
    setHolding(true);
    onHoldStart?.();
    if (!quiet) void haptic(Haptics.ImpactFeedbackStyle.Medium);
    Animated.timing(progress, { toValue: 1, duration: HOLD_MS, easing: Easing.linear, useNativeDriver: false }).start();
    timer.current = setTimeout(() => {
      timer.current = null;
      setHolding(false);
      progress.setValue(0);
      if (!quiet) void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning).catch(() => {});
      onTrigger();
    }, HOLD_MS);
  };

  const stop = () => {
    if (timer.current) {
      clearTimeout(timer.current);
      timer.current = null;
    }
    setHolding(false);
    progress.stopAnimation();
    progress.setValue(0);
  };

  const confirm = () =>
    Alert.alert(t("estate.panic.confirmTitle"), t("estate.panic.confirmBody"), [
      { text: t("common.cancel"), style: "cancel" },
      {
        text: t("estate.panic.confirmSend"),
        style: "destructive",
        onPress: () => {
          onHoldStart?.();
          onTrigger();
        },
      },
    ]);

  const size = 200;
  return (
    <View className="items-center gap-3">
      <Pressable
        testID="panic-button"
        accessibilityRole="button"
        accessibilityLabel={t("estate.panic.label")}
        accessibilityHint={t("estate.panic.a11yHint")}
        accessibilityState={{ disabled: !!disabled }}
        accessibilityActions={[{ name: "activate", label: t("estate.panic.confirmSend") }]}
        onAccessibilityAction={(e) => e.nativeEvent.actionName === "activate" && confirm()}
        onPressIn={start}
        onPressOut={stop}
        disabled={disabled}
        style={{
          width: size,
          height: size,
          borderRadius: size / 2,
          backgroundColor: holding ? tokens.color.emergency.pressed : tokens.color.emergency.base,
          borderWidth: 10,
          borderColor: tokens.color.emergency.glow,
          alignItems: "center",
          justifyContent: "center",
          opacity: disabled ? 0.5 : 1,
          overflow: "hidden",
        }}
      >
        <Animated.View
          pointerEvents="none"
          style={{
            position: "absolute",
            bottom: 0,
            left: 0,
            right: 0,
            height: progress.interpolate({ inputRange: [0, 1], outputRange: [0, size] }),
            backgroundColor: tokens.color.emergency.pressed,
          }}
        />
        <Text variant="heading" style={{ color: tokens.color.emergency.on, textAlign: "center" }}>
          {holding ? t("estate.panic.holding") : t("estate.panic.hold")}
        </Text>
      </Pressable>
      <Text className="text-center text-ink-600">{t("estate.panic.hint")}</Text>
    </View>
  );
}

/** A labelled native switch (large touch target, announced as a switch). */
export function ToggleRow({ label, hint, value, onChange }: { label: string; hint: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <View className="min-h-12 flex-row items-center gap-3">
      <View className="flex-1">
        <Text variant="label">{label}</Text>
        <Text variant="caption" className="text-ink-600">
          {hint}
        </Text>
      </View>
      <Switch
        accessibilityLabel={label}
        accessibilityHint={hint}
        value={value}
        onValueChange={onChange}
        trackColor={{ true: tokens.color.primary[600], false: tokens.color.ink[400] }}
      />
    </View>
  );
}

/** "What's happening?" choices after the alert is sent. */
export function KindChips({ value, onPick, disabled }: { value: PanicKind; onPick: (k: PanicKind) => void; disabled?: boolean }) {
  const { t } = useTranslation();
  return (
    <View className="flex-row flex-wrap gap-2" accessibilityRole="radiogroup" accessibilityLabel={t("estate.panic.whatsHappening")}>
      {PANIC_KINDS.map((k) => {
        const selected = k === value;
        return (
          <Pressable
            key={k}
            accessibilityRole="radio"
            accessibilityState={{ selected, disabled: !!disabled }}
            disabled={disabled}
            onPress={() => onPick(k)}
            className={`min-h-12 justify-center rounded-pill border-2 px-4 ${selected ? "border-primary-600 bg-primary-600" : "border-surface-line bg-white"}`}
          >
            <Text variant="label" className={selected ? "text-white" : "text-ink-800"}>
              {t(`estate.panic.kind.${k}`)}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}
