import { Ionicons } from "@expo/vector-icons";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Alert, FlatList, Pressable, TextInput, View } from "react-native";
import { useReducedMotion } from "react-native-reanimated";

import { MAX_CHAT_CHARS } from "@/api";
import {
  ActionCard,
  Banner,
  ChatBubble,
  EmptyState,
  ListRow,
  Screen,
  SkeletonCard,
  SuggestionChip,
  Text,
  TypingIndicator,
} from "@/components";
import { useAssistantChat, type Bubble } from "@/hooks/useAssistantChat";
import tokens from "@/theme/tokens";

/** Show the character counter once the message gets close to the limit. */
const COUNTER_FROM = MAX_CHAT_CHARS - 200;

const SUGGESTIONS = ["owe", "receipts", "nextDue"] as const;

/** Chat with the Homesika assistant (rent, payments, receipts, lease, how to use the app). */
export default function Help() {
  const { t } = useTranslation();
  const chat = useAssistantChat();
  const [draft, setDraft] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const list = useRef<FlatList<Bubble>>(null);
  const reduceMotion = useReducedMotion();

  const items = chat.state?.items ?? [];
  const pending = chat.state?.pending ?? null;
  const sending = chat.busy === "send";
  const tooLong = draft.trim().length > MAX_CHAT_CHARS;
  const canSend = draft.trim().length > 0 && !tooLong && chat.busy === null && !chat.loading;

  const submit = (text = draft) => {
    if (chat.send(text) && text === draft) setDraft("");
  };

  const confirmClear = () => {
    setMenuOpen(false);
    Alert.alert(t("help.clearTitle"), t("help.clearBody"), [
      { text: t("common.cancel"), style: "cancel" },
      { text: t("help.clearConfirm"), style: "destructive", onPress: () => void chat.clear() },
    ]);
  };

  const menuButton = (
    <Pressable
      onPress={() => setMenuOpen((o) => !o)}
      accessibilityRole="button"
      accessibilityLabel={t("help.menu")}
      accessibilityState={{ expanded: menuOpen }}
      className="h-12 w-12 items-center justify-center rounded-full"
    >
      <Ionicons name="ellipsis-vertical" size={24} color={tokens.color.ink.inverse} />
    </Pressable>
  );

  const empty = chat.loading ? (
    <SkeletonCard label={t("common.loading")} />
  ) : chat.loadError ? (
    <Banner message={`${t("errors.loadFailed")} ${chat.loadError}`} onRetry={chat.reload} retryLabel={t("common.retry")} />
  ) : (
    <View className="gap-4">
      <EmptyState icon="chatbubbles-outline" title={t("help.emptyTitle")} body={t("help.emptyBody")} />
      <Text variant="label">{t("help.suggestionsLabel")}</Text>
      <View className="flex-row flex-wrap gap-3">
        {SUGGESTIONS.map((k) => (
          <SuggestionChip key={k} label={t(`help.suggestions.${k}`)} disabled={chat.busy !== null} onPress={() => submit(t(`help.suggestions.${k}`))} />
        ))}
      </View>
      {/* Information only: the emergency red is reserved for the panic button (Phase 5). */}
      <View className="flex-row items-center gap-3 rounded-md border border-surface-line bg-surface-card px-4 py-3" accessible>
        <Ionicons name="call-outline" size={22} color={tokens.color.primary[800]} />
        <Text className="flex-1">{t("help.emergency")}</Text>
      </View>
    </View>
  );

  const composer = (
    <View className="gap-1">
      <View className="flex-row items-end gap-2">
        <TextInput
          value={draft}
          onChangeText={setDraft}
          placeholder={t("help.placeholder")}
          placeholderTextColor={tokens.color.ink[500]}
          accessibilityLabel={t("help.inputLabel")}
          multiline
          maxLength={MAX_CHAT_CHARS}
          maxFontSizeMultiplier={2}
          testID="chat-input"
          className="max-h-32 min-h-12 flex-1 rounded-md border-2 border-ink-400 bg-white px-3 py-3 font-sans text-base text-ink-900"
        />
        <Pressable
          onPress={() => submit()}
          disabled={!canSend}
          accessibilityRole="button"
          accessibilityLabel={t("help.send")}
          accessibilityState={{ disabled: !canSend, busy: sending }}
          className={`h-12 w-12 items-center justify-center rounded-full bg-primary-600 active:bg-primary-700 ${canSend ? "" : "opacity-50"}`}
        >
          <Ionicons name="send" size={22} color={tokens.color.ink.inverse} />
        </Pressable>
      </View>
      {draft.length >= COUNTER_FROM ? (
        <Text
          variant="caption"
          className={`text-right ${draft.length >= MAX_CHAT_CHARS ? "text-warning-700" : ""}`}
          accessibilityLiveRegion="polite"
        >
          {t("help.counter", { count: draft.length, max: MAX_CHAT_CHARS })}
        </Text>
      ) : null}
    </View>
  );

  return (
    <Screen title={t("help.title")} headerRight={menuButton} scroll={false} footer={composer}>
      {menuOpen ? (
        <View className="rounded-md border border-surface-line bg-surface-card px-4">
          <ListRow title={t("help.clear")} onPress={confirmClear} leading={<Ionicons name="trash-outline" size={22} color={tokens.color.ink[700]} />} />
        </View>
      ) : null}
      {chat.state?.escalated ? <Banner tone="info" message={t("help.escalated")} /> : null}
      {chat.error ? <Banner message={chat.error} /> : null}
      <FlatList
        ref={list}
        data={items}
        keyExtractor={(b) => b.key}
        renderItem={({ item }) => <ChatBubble bubble={item} onRetry={() => chat.retry(item.key)} />}
        contentContainerStyle={{ gap: 12, paddingBottom: 16, flexGrow: 1 }}
        keyboardShouldPersistTaps="handled"
        onContentSizeChange={() => list.current?.scrollToEnd({ animated: !reduceMotion })}
        ListEmptyComponent={empty}
        ListFooterComponent={
          <View className="gap-3">
            {sending ? <TypingIndicator /> : null}
            {pending ? (
              <ActionCard
                action={pending}
                busy={chat.busy}
                onConfirm={() => void chat.decide("confirm")}
                onReject={() => void chat.decide("reject")}
              />
            ) : null}
          </View>
        }
        initialNumToRender={15}
        windowSize={7}
      />
    </Screen>
  );
}
