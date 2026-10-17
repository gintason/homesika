import { Ionicons } from "@expo/vector-icons";
import { useTranslation } from "react-i18next";
import { Image, Pressable, View } from "react-native";

import type { TicketEvent, TicketPhoto, TicketPriority, TicketStatus } from "@/api";
import { formatDateTime } from "@/lib/date";
import { pickPhoto, type PhotoFile } from "@/lib/photos";
import tokens from "@/theme/tokens";

import { Button } from "./Button";
import { Text } from "./Text";

type Tone = "info" | "warning" | "success" | "neutral" | "danger" | "gold";

const TONES: Record<Tone, { box: string; text: string }> = {
  info: { box: "bg-primary-50", text: "text-primary-700" },
  warning: { box: "bg-warning-50", text: "text-warning-700" },
  success: { box: "bg-success-50", text: "text-success-700" },
  neutral: { box: "bg-surface-muted", text: "text-ink-700" },
  danger: { box: "bg-danger-50", text: "text-danger-700" },
  gold: { box: "bg-gold-50", text: "text-gold-700" },
};

/** A status chip. Colour is never the only signal: the label always says it. */
export function ToneBadge({ tone, label }: { tone: Tone; label: string }) {
  const s = TONES[tone];
  return (
    <View className={`self-start rounded-pill px-3 py-1 ${s.box}`}>
      <Text variant="caption" className={`font-semibold ${s.text}`}>
        {label}
      </Text>
    </View>
  );
}

const STATUS_TONE: Record<TicketStatus, Tone> = {
  awaiting_approval: "warning",
  approved: "info",
  assigned: "info",
  in_progress: "info",
  done: "gold",
  confirmed: "success",
  rejected: "neutral",
  cancelled: "neutral",
};

export function TicketStatusBadge({ status }: { status: TicketStatus }) {
  const { t } = useTranslation();
  return <ToneBadge tone={STATUS_TONE[status] ?? "neutral"} label={t(`repairs.status.${status}`)} />;
}

/** Only urgent and emergency are badged. Emergency uses the danger tone, not the panic-button red. */
export function PriorityBadge({ priority }: { priority: TicketPriority }) {
  const { t } = useTranslation();
  if (priority === "emergency") return <ToneBadge tone="danger" label={t("repairs.priority.emergency")} />;
  if (priority === "urgent") return <ToneBadge tone="warning" label={t("repairs.priority.urgent")} />;
  return null;
}

export function VerifiedBadge() {
  const { t } = useTranslation();
  return (
    <View
      className="flex-row items-center gap-1 self-start rounded-pill bg-success-50 px-3 py-1"
      accessible
      accessibilityLabel={t("repairs.detail.verified")}
      accessibilityHint={t("repairs.detail.verifiedHint")}
    >
      <Ionicons name="shield-checkmark" size={16} color={tokens.color.success[700]} />
      <Text variant="caption" className="font-semibold text-success-700">
        {t("repairs.detail.verified")}
      </Text>
    </View>
  );
}

/** "4.8 from 5 ratings · 12 jobs done" (or "New on Homesika"). */
export function ArtisanStats({ avg, count, jobs }: { avg: number | null; count: number; jobs: number }) {
  const { t } = useTranslation();
  const rating = avg === null ? t("repairs.detail.noRatings") : t("repairs.detail.rating", { avg: avg.toFixed(1), count });
  return <Text variant="caption">{`${rating} · ${t("repairs.detail.jobs", { count: jobs })}`}</Text>;
}

/** Photos in a 3-column grid. Links are signed and short-lived, so they're refetched with the ticket. */
export function PhotoGrid({ photos }: { photos: TicketPhoto[] }) {
  const { t } = useTranslation();
  if (!photos.length) return null;
  return (
    <View className="flex-row flex-wrap gap-2">
      {photos.map((p, i) =>
        p.url ? (
          <Image
            key={p.id}
            source={{ uri: p.url }}
            accessibilityLabel={t("repairs.form.photoAlt", { n: i + 1 })}
            className="h-24 w-24 rounded-md bg-surface-muted"
            resizeMode="cover"
          />
        ) : null,
      )}
    </View>
  );
}

/** Two buttons: camera and gallery. Calls back with a shrunk JPEG ready to upload. */
export function PhotoButtons({
  onPicked,
  onDenied,
  disabled,
  cameraLabel,
  galleryLabel,
}: {
  onPicked: (photo: PhotoFile) => void;
  onDenied: () => void;
  disabled?: boolean;
  cameraLabel?: string;
  galleryLabel?: string;
}) {
  const { t } = useTranslation();
  const pick = async (source: "camera" | "library") => {
    const r = await pickPhoto(source);
    if (r.kind === "picked") onPicked(r.photo);
    else if (r.kind === "denied") onDenied();
  };
  return (
    <View className="flex-row flex-wrap gap-3">
      <Button
        title={cameraLabel ?? t("repairs.form.takePhoto")}
        variant="secondary"
        disabled={disabled}
        onPress={() => void pick("camera")}
        className="grow"
      />
      <Button
        title={galleryLabel ?? t("repairs.form.choosePhoto")}
        variant="ghost"
        disabled={disabled}
        onPress={() => void pick("library")}
        className="grow"
      />
    </View>
  );
}

/** Timeline of a ticket (internal staff notes never reach the app). */
export function Timeline({ events }: { events: TicketEvent[] }) {
  const { t } = useTranslation();
  return (
    <View className="gap-3">
      {events.map((e) => (
        <View key={e.id} className="gap-1 border-l-2 border-surface-line pl-3">
          <Text variant="label">{t(`repairs.events.${e.kind}`, { defaultValue: e.kind })}</Text>
          <Text variant="caption">
            {formatDateTime(e.created_at)}
            {e.actor_role ? ` · ${t(`repairs.roles.${e.actor_role}`)}` : ""}
            {e.actor_name && e.actor_role !== "tenant" ? ` · ${e.actor_name}` : ""}
          </Text>
          {e.note ? <Text>{e.note}</Text> : null}
        </View>
      ))}
    </View>
  );
}

/** 1-5 stars; each star is a 48×48 radio with a spoken label. */
export function StarPicker({ value, onChange, label }: { value: number; onChange: (n: number) => void; label: string }) {
  const { t } = useTranslation();
  return (
    <View className="flex-row gap-1" accessibilityRole="radiogroup" accessibilityLabel={label}>
      {[1, 2, 3, 4, 5].map((n) => (
        <Pressable
          key={n}
          onPress={() => onChange(n)}
          accessibilityRole="radio"
          accessibilityState={{ selected: value === n, checked: value === n }}
          accessibilityLabel={n === 1 ? t("repairs.detail.star", { count: n }) : t("repairs.detail.stars", { count: n })}
          className="h-12 w-12 items-center justify-center"
        >
          <Ionicons name={n <= value ? "star" : "star-outline"} size={32} color={tokens.color.gold[500]} />
        </Pressable>
      ))}
    </View>
  );
}
