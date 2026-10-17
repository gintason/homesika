import { useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Linking, View } from "react-native";

import { repairsApi, type Ticket } from "@/api";
import { Banner, Button, Card, Screen, SkeletonCard, Text, TextField } from "@/components";
import { PhotoButtons, PhotoGrid, PriorityBadge, StarPicker, TicketStatusBadge, Timeline, VerifiedBadge, ArtisanStats } from "@/components/repairs";
import { keys, useTicket } from "@/hooks/queries";
import { errorText } from "@/lib/api";
import { formatDate, formatDateTime } from "@/lib/date";
import { photoForm } from "@/lib/photos";

type Busy = "confirm" | "reopen" | "rate" | "cancel" | "comment" | "photo" | null;

/** One repair request: what's happening, who's coming, and what I can do next (ticket.can). */
export default function RepairDetail() {
  const { t } = useTranslation();
  const { id = "", photosFailed } = useLocalSearchParams<{ id: string; photosFailed?: string }>();
  const q = useTicket(id);
  const qc = useQueryClient();
  const [busy, setBusy] = useState<Busy>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(
    photosFailed ? t("repairs.form.photosFailed", { count: Number(photosFailed) }) : null,
  );
  const [reopenNote, setReopenNote] = useState("");
  const [reopening, setReopening] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [cancelReason, setCancelReason] = useState("");
  const [score, setScore] = useState(0);
  const [rateComment, setRateComment] = useState("");
  const [comment, setComment] = useState("");

  const ticket = q.data;
  if (!ticket) {
    return (
      <Screen title={t("repairs.title")} back>
        {q.error ? (
          <Banner message={`${t("errors.loadFailed")} ${errorText(q.error)}`} onRetry={() => q.refetch()} retryLabel={t("common.retry")} />
        ) : (
          <SkeletonCard label={t("common.loading")} />
        )}
      </Screen>
    );
  }
  const can = (a: Ticket["can"][number]) => ticket.can.includes(a);

  const run = async (kind: NonNullable<Busy>, fn: () => Promise<unknown>, done: string) => {
    setBusy(kind);
    setError(null);
    try {
      await fn();
      setNotice(done);
      await Promise.all([qc.invalidateQueries({ queryKey: keys.ticket(id) }), qc.invalidateQueries({ queryKey: keys.tickets })]);
      return true;
    } catch (e) {
      setError(errorText(e));
      return false;
    } finally {
      setBusy(null);
    }
  };

  const job = ticket.job;
  return (
    <Screen title={t("repairs.detail.title", { reference: ticket.reference })} back onRefresh={() => q.refetch()} refreshing={q.isRefetching}>
      {notice ? <Banner tone="success" message={notice} /> : null}
      {error ? <Banner message={error} /> : null}

      <Card>
        <View className="flex-row flex-wrap gap-2">
          <TicketStatusBadge status={ticket.status} />
          <PriorityBadge priority={ticket.priority} />
        </View>
        <Text variant="heading" accessibilityRole="header">
          {ticket.title}
        </Text>
        <Text variant="caption">
          {t(`repairs.category.${ticket.category}`)} · {ticket.unit.label}, {ticket.unit.property} ·{" "}
          {t("repairs.detail.reported", { date: formatDate(ticket.created_at) })}
        </Text>
        <Text>{ticket.description}</Text>
        {ticket.access_notes ? <Text variant="caption">{`${t("repairs.detail.access")}: ${ticket.access_notes}`}</Text> : null}
        {ticket.closed_reason ? <Text variant="caption">{t("repairs.detail.reason", { reason: ticket.closed_reason })}</Text> : null}
        {ticket.auto_confirmed ? <Text variant="caption">{t("repairs.detail.autoConfirmed")}</Text> : null}
      </Card>

      {can("confirm") ? (
        <Card>
          <Text variant="heading" accessibilityRole="header">
            {t("repairs.detail.confirmTitle")}
          </Text>
          <Text>{t("repairs.detail.confirmBody")}</Text>
          {job?.completion_note ? <Text variant="caption">{job.completion_note}</Text> : null}
          <Button
            title={t("repairs.detail.confirm")}
            loading={busy === "confirm"}
            disabled={busy !== null}
            onPress={() => void run("confirm", () => repairsApi.confirm(id), t("repairs.detail.confirmed"))}
          />
          {reopening ? (
            <>
              <TextField label={t("repairs.detail.reopenLabel")} value={reopenNote} onChangeText={setReopenNote} multiline maxLength={1000} />
              <Button
                title={t("repairs.detail.reopenSend")}
                variant="secondary"
                loading={busy === "reopen"}
                disabled={busy !== null || !reopenNote.trim()}
                onPress={() =>
                  void run("reopen", () => repairsApi.reopen(id, reopenNote.trim()), t("repairs.detail.reopened")).then((ok) => {
                    if (ok) setReopening(false);
                  })
                }
              />
            </>
          ) : (
            <Button title={t("repairs.detail.reopen")} variant="secondary" disabled={busy !== null} onPress={() => setReopening(true)} />
          )}
        </Card>
      ) : null}

      {can("rate") ? (
        <Card>
          <Text variant="heading" accessibilityRole="header">
            {t("repairs.detail.rateTitle")}
          </Text>
          <Text>{t("repairs.detail.rateBody")}</Text>
          <StarPicker value={score} onChange={setScore} label={t("repairs.detail.rateTitle")} />
          <TextField label={t("repairs.detail.rateComment")} value={rateComment} onChangeText={setRateComment} maxLength={500} />
          <Button
            title={t("repairs.detail.rateSend")}
            loading={busy === "rate"}
            disabled={busy !== null || score === 0}
            onPress={() => void run("rate", () => repairsApi.rate(id, score, rateComment.trim()), t("repairs.detail.rated"))}
          />
        </Card>
      ) : null}

      <Card>
        <Text variant="heading" accessibilityRole="header">
          {t("repairs.detail.artisan")}
        </Text>
        {job ? (
          <>
            <View className="flex-row flex-wrap items-center gap-2">
              <Text variant="label">{job.artisan.display_name}</Text>
              {job.artisan.is_verified ? <VerifiedBadge /> : null}
            </View>
            <ArtisanStats avg={job.artisan.rating_avg} count={job.artisan.rating_count} jobs={job.artisan.jobs_completed} />
            {job.scheduled_for ? <Text>{t("repairs.detail.visit", { when: formatDateTime(job.scheduled_for) })}</Text> : null}
            {job.artisan.phone_number ? (
              <Button
                title={t("repairs.detail.call", { name: job.artisan.display_name })}
                variant="secondary"
                onPress={() => void Linking.openURL(`tel:${job.artisan.phone_number}`)}
              />
            ) : null}
            {ticket.rating ? <Text variant="caption">{t("repairs.detail.yourRating", { score: ticket.rating.score })}</Text> : null}
          </>
        ) : (
          <Text>{t("repairs.detail.noArtisan")}</Text>
        )}
        <Text variant="caption">{t("repairs.detail.noPayment")}</Text>
      </Card>

      <Card>
        <Text variant="heading" accessibilityRole="header">
          {t("repairs.detail.photos")}
        </Text>
        <PhotoGrid photos={ticket.photos} />
        {can("photo") ? (
          <PhotoButtons
            disabled={busy !== null}
            onPicked={(p) => void run("photo", () => repairsApi.addPhoto(id, photoForm(p)), t("repairs.detail.photoAdded"))}
            onDenied={() => setError(t("repairs.form.permission"))}
          />
        ) : null}
      </Card>

      {can("comment") ? (
        <Card>
          <TextField
            label={t("repairs.detail.comment")}
            hint={t("repairs.detail.commentHint")}
            value={comment}
            onChangeText={setComment}
            multiline
            maxLength={1000}
          />
          <Button
            title={t("repairs.detail.commentSend")}
            variant="secondary"
            loading={busy === "comment"}
            disabled={busy !== null || !comment.trim()}
            onPress={() =>
              void run("comment", () => repairsApi.comment(id, comment.trim()), t("repairs.detail.commented")).then((ok) => {
                if (ok) setComment("");
              })
            }
          />
        </Card>
      ) : null}

      <Card>
        <Text variant="heading" accessibilityRole="header">
          {t("repairs.detail.timeline")}
        </Text>
        <Timeline events={ticket.events} />
      </Card>

      {can("cancel") ? (
        cancelling ? (
          <Card>
            <TextField label={t("repairs.detail.cancelLabel")} value={cancelReason} onChangeText={setCancelReason} maxLength={300} />
            <Button
              title={t("repairs.detail.cancelConfirm")}
              variant="destructive"
              loading={busy === "cancel"}
              disabled={busy !== null}
              onPress={() =>
                void run("cancel", () => repairsApi.cancel(id, cancelReason.trim()), t("repairs.detail.cancelled")).then((ok) => {
                  if (ok) setCancelling(false);
                })
              }
            />
          </Card>
        ) : (
          <Button title={t("repairs.detail.cancel")} variant="ghost" onPress={() => setCancelling(true)} />
        )
      ) : null}
    </Screen>
  );
}
