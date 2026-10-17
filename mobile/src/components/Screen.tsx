import { Ionicons } from "@expo/vector-icons";
import { router } from "expo-router";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { KeyboardAvoidingView, Platform, Pressable, RefreshControl, ScrollView, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { useOnline } from "@/hooks/useOnline";
import tokens from "@/theme/tokens";

import { Banner } from "./Banner";
import { Text } from "./Text";

type Props = {
  children: ReactNode;
  /** Navy header with this title (tab screens). */
  title?: string;
  back?: boolean;
  /** Extra header controls on the right (e.g. a menu button). */
  headerRight?: ReactNode;
  scroll?: boolean;
  footer?: ReactNode;
  /** Pull-to-refresh. */
  onRefresh?: () => void;
  refreshing?: boolean;
  className?: string;
};

/**
 * Standard screen: safe area, app background, optional navy header (primary.800) or back button,
 * offline banner, keyboard-aware scroll with pull-to-refresh, and a pinned footer.
 */
export function Screen({ children, title, back, headerRight, scroll = true, footer, onRefresh, refreshing = false, className = "" }: Props) {
  const { t } = useTranslation();
  const online = useOnline();
  const navy = Boolean(title);

  const body = (
    <View className={`flex-1 gap-5 px-5 pb-6 pt-4 ${className}`}>
      {!online ? <Banner tone="offline" message={t("errors.offline")} /> : null}
      {children}
    </View>
  );

  return (
    <SafeAreaView
      className={`flex-1 ${navy ? "bg-primary-800" : "bg-surface-background"}`}
      edges={["top", "left", "right"]}
    >
      {navy || back ? (
        <View className={`min-h-12 flex-row items-center gap-2 px-3 py-2 ${navy ? "bg-primary-800" : ""}`}>
          {back ? (
            <Pressable
              onPress={() => (router.canGoBack() ? router.back() : router.replace("/"))}
              hitSlop={8}
              className="h-12 w-12 items-center justify-center rounded-full"
              accessibilityRole="button"
              accessibilityLabel={t("common.back")}
            >
              <Ionicons name="chevron-back" size={26} color={navy ? tokens.color.ink.inverse : tokens.color.ink[800]} />
            </Pressable>
          ) : null}
          {title ? (
            <Text variant="heading" className={`flex-1 text-white ${back ? "" : "px-2"}`} accessibilityRole="header">
              {title}
            </Text>
          ) : null}
          {headerRight}
        </View>
      ) : null}
      <KeyboardAvoidingView
        className="flex-1 bg-surface-background"
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        {scroll ? (
          <ScrollView
            contentContainerStyle={{ flexGrow: 1 }}
            keyboardShouldPersistTaps="handled"
            refreshControl={
              onRefresh ? (
                <RefreshControl
                  refreshing={refreshing}
                  onRefresh={onRefresh}
                  tintColor={tokens.color.primary[600]}
                  colors={[tokens.color.primary[600]]}
                  accessibilityLabel={t("a11y.refresh")}
                />
              ) : undefined
            }
          >
            {body}
          </ScrollView>
        ) : (
          body
        )}
        {footer ? (
          <SafeAreaView edges={["bottom"]} className="border-t border-surface-line bg-surface-card px-5 pb-3 pt-3">
            {footer}
          </SafeAreaView>
        ) : null}
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
