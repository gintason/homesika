import { Ionicons } from "@expo/vector-icons";
import { useTranslation } from "react-i18next";
import { ActivityIndicator, Pressable, View } from "react-native";

import type { PendingAction } from "@/api";
import type { Bubble } from "@/hooks/useAssistantChat";
import { hostOf, linkify, linksIn, openChatLink, payReference } from "@/lib/links";
import tokens from "@/theme/tokens";

import { Button } from "./Button";
import { Card } from "./Card";
import { Text } from "./Text";

/** One message. Mine on the right (brand blue), the assistant's on the left (card). Links open in-app. */
export function ChatBubble({ bubble, onRetry }: { bubble: Bubble; onRetry?: () => void }) {
  const { t } = useTranslation();
  const mine = bubble.mine;
  const who = mine ? t("help.you") : bubble.from ? t("help.fromPerson", { name: bubble.from }) : t("help.assistant");
  const links = mine ? [] : linksIn(bubble.text).slice(0, 3);
  return (
    <View className={`max-w-[85%] gap-1 ${mine ? "self-end items-end" : "self-start items-start"}`}>
      {bubble.from ? <Text variant="caption">{who}</Text> : null}
      <View
        accessible
        accessibilityLabel={`${who}: ${bubble.text}`}
        className={`rounded-lg px-4 py-3 ${mine ? "bg-primary-600" : "border border-surface-line bg-surface-card"} ${bubble.state === "failed" ? "opacity-70" : ""}`}
      >
        <Text className={mine ? "text-white" : "text-ink-800"} selectable>
          {linkify(bubble.text).map((s, i) =>
            s.url ? (
              <Text
                key={i}
                accessibilityRole="link"
                onPress={() => openChatLink(s.url!)}
                className={`underline ${mine ? "text-white" : "text-primary-600"}`}
              >
                {s.text}
              </Text>
            ) : (
              s.text
            ),
          )}
        </Text>
      </View>
      {/* Links again as real 48pt buttons: inline links are too small to hit and hard to reach with a screen reader. */}
      {links.map((url) => (
        <Pressable
          key={url}
          onPress={() => openChatLink(url)}
          accessibilityRole="link"
          accessibilityLabel={payReference(url) ? t("help.payLink") : t("help.openLink", { host: hostOf(url) })}
          className="min-h-12 flex-row items-center gap-2 rounded-pill border-2 border-primary-600 bg-white px-4 active:bg-primary-50"
        >
          <Ionicons name={payReference(url) ? "card-outline" : "open-outline"} size={20} color={tokens.color.primary[600]} />
          <Text variant="label" className="text-primary-600">
            {payReference(url) ? t("help.payLink") : t("help.openLink", { host: hostOf(url) })}
          </Text>
        </Pressable>
      ))}
      {bubble.state === "sending" ? <Text variant="caption">{t("help.sending")}</Text> : null}
      {bubble.state === "failed" ? (
        <Pressable
          onPress={onRetry}
          accessibilityRole="button"
          accessibilityLabel={t("help.notSent")}
          accessibilityHint={bubble.error}
          className="min-h-12 flex-row items-center gap-2 rounded-pill bg-warning-50 px-4"
        >
          <Ionicons name="refresh" size={20} color={tokens.color.warning[700]} />
          <Text variant="label" className="text-warning-700">
            {t("help.notSent")}
          </Text>
        </Pressable>
      ) : null}
    </View>
  );
}

/** "Homesika is typing…": a static bubble with the system spinner (no custom animation to switch off). */
export function TypingIndicator() {
  const { t } = useTranslation();
  return (
    <View
      className="flex-row items-center gap-2 self-start rounded-lg border border-surface-line bg-surface-card px-4 py-3"
      accessible
      accessibilityLabel={t("help.typing")}
      accessibilityLiveRegion="polite"
      testID="typing"
    >
      <ActivityIndicator size="small" color={tokens.color.primary[600]} />
      <Text className="text-ink-600">{t("help.typing")}</Text>
    </View>
  );
}

type ActionProps = {
  action: PendingAction;
  busy: null | "confirm" | "reject" | string;
  onConfirm: () => void;
  onReject: () => void;
};

/** The assistant proposed something (a pay link, a viewing). Nothing happens until Confirm. */
export function ActionCard({ action, busy, onConfirm, onReject }: ActionProps) {
  const { t } = useTranslation();
  return (
    <Card className="border-primary-300">
      <View className="flex-row items-center gap-2">
        <Ionicons name="help-circle-outline" size={24} color={tokens.color.primary[600]} />
        <Text variant="label" accessibilityRole="header">
          {t("help.confirmTitle")}
        </Text>
      </View>
      <Text>{action.summary}</Text>
      <View className="flex-row flex-wrap gap-3">
        <Button
          title={t("help.confirm")}
          className="flex-1"
          loading={busy === "confirm"}
          disabled={busy !== null && busy !== "confirm"}
          onPress={onConfirm}
        />
        <Button
          title={t("help.cancelAction")}
          variant="secondary"
          className="flex-1"
          loading={busy === "reject"}
          disabled={busy !== null && busy !== "reject"}
          onPress={onReject}
        />
      </View>
    </Card>
  );
}

/** A suggested question for a new chat (pill, 48pt tall). */
export function SuggestionChip({ label, onPress, disabled }: { label: string; onPress: () => void; disabled?: boolean }) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled: !!disabled }}
      className="min-h-12 justify-center rounded-pill border-2 border-primary-300 bg-white px-4 active:bg-primary-50"
    >
      <Text variant="label" className="text-primary-700">
        {label}
      </Text>
    </Pressable>
  );
}
