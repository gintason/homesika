import { useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams } from "expo-router";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Linking, View } from "react-native";

import { artisanApi, type ArtisanJob } from "@/api";
import { Banner, Button, Card, Screen, SkeletonCard, Text, TextField } from "@/components";
import { ChoiceChips } from "@/components/bills";
import { PhotoButtons, PhotoGrid, PriorityBadge, ToneBadge, Timeline } from "@/components/repairs";
import { keys, useJob } from "@/hooks/queries";
import { errorText } from "@/lib/api";
import { formatDateTime } from "@/lib/date";
import { photoForm } from "@/lib/photos";
import { formatPhone } from "@/lib/phone";
import { visitChoices } from "@/lib/repairs";

type Busy = "accept" | "decline" | "schedule" | "start" | "complete" | "photo" | "comment" | null;

export default function JobDetail() {
  const { t } = useTranslation();
  const { id = "" } = useLocalSearchParams<{ id: string }>();
  const q = useJob(id);
  const qc = useQueryClient();
  const [busy, setBusy] = useState<Busy>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [when, setWhen] = useState<string>("later");
  const [reason, setReason] = useState("");
  const [declining, setDeclining] = useState(false);
  const [note, setNote] = useState("");
  const [completing, setCompleting] = useState(false);
  const [comment, setComment] = useState("");
  const choices = useMemo(() => visitChoices(), []);

  const job = q.data;
  if (!job) {
    return (
      <Screen title={t("work.jobs")} back>
        {q.error ? (
          <Banner message={`${t("errors.loadFailed")} ${errorText(q.error)}`} onRetry={() => q.refetch()} retryLabel={t("common.retry")} />
        ) : (
          <SkeletonCard label={t("common.loading")} />
        )}
      </Screen>
    );
  }
  const can = (a: ArtisanJob["can"][number]) => job.can.includes(a);

  const run = async (kind: NonNullable<Busy>, fn: () => Promise<unknown>, done: string) => {
    setBusy(kind);
    setError(null);
    try {
      await fn();
      setNotice(done);
      await Promise.all([
        qc.invalidateQueries({ queryKey: keys.job(id) }),
        qc.invalidateQueries({ queryKey: ["me", "jobs"] }),
      ]);
      return true;
    } catch (e) {
      setError(errorText(e));
      return false;
    } finally {
      setBusy(null);
    }
  };

  const whenChoices = [
    ...choices.map((c) => ({ value: c.value, label: `${t(`work.job.${c.day}`)}, ${t(`work.job.${c.part}`)}` })),
    { value: "later", label: t("work.job.decideLater") },
  ];
  const tk = job.ticket;

  return (
    <Screen title={t("work.job.title", { reference: tk.reference })} back onRefresh={() => q.refetch()} refreshing={q.isRefetching}>
      {notice ? <Banner tone="success" message={notice} /> : null}
      {error ? <Banner message={error} /> : null}

      <Card>
        <View className="flex-row flex-wrap gap-2">
          <ToneBadge tone={job.status === "offered" ? "gold" : "info"} label={t(`work.job.status.${job.status}`)} />
          <PriorityBadge priority={tk.priority} />
        </View>
        <Text variant="heading" accessibilityRole="header">
          {tk.title}
        </Text>
        <Text variant="caption">
          {t(`repairs.category.${tk.category}`)} · {t("work.job.from", { org: job.organization })}
        </Text>
        <Text>{tk.description}</Text>
        {job.offer_note ? <Text variant="caption">{`${t("work.job.note")}: ${job.offer_note}`}</Text> : null}
        {job.status === "offered" ? <Text variant="caption">{t("work.job.acceptBy", { when: formatDateTime(job.offer_expires_at) })}</Text> : null}
        {job.scheduled_for ? <Text>{t("work.job.visit", { when: formatDateTime(job.scheduled_for) })}</Text> : null}
        {job.rating ? <Text variant="caption">{t("work.job.rating", { score: job.rating.score })}</Text> : null}
      </Card>

      <Card>
        <Text variant="label">{job.location.address ? t("work.job.address") : t("work.job.area", { area: job.location.area })}</Text>
        {job.location.address ? (
          <Text>{[job.location.unit, job.location.property, job.location.address].filter(Boolean).join(", ")}</Text>
        ) : (
          <Text variant="caption">{t("work.job.addressAfter")}</Text>
        )}
        {tk.access_notes ? <Text variant="caption">{`${t("work.job.access")}: ${tk.access_notes}`}</Text> : null}
        {job.contact ? (
          <>
            <Text variant="label">{`${t("work.job.contact")}: ${job.contact.name} · ${formatPhone(job.contact.phone_number)}`}</Text>
            <Button
              title={t("work.job.call", { name: job.contact.name })}
              variant="secondary"
              onPress={() => void Linking.openURL(`tel:${job.contact!.phone_number}`)}
            />
          </>
        ) : null}
      </Card>

      {can("accept") ? (
        <Card>
          <ChoiceChips label={t("work.job.when")} value={when} onChange={setWhen} choices={whenChoices} />
          <Button
            title={t("work.job.accept")}
            loading={busy === "accept"}
            disabled={busy !== null}
            onPress={() => void run("accept", () => artisanApi.accept(id, when === "later" ? null : when), t("work.job.accepted"))}
          />
          {declining ? (
            <>
              <TextField label={t("work.job.declineLabel")} value={reason} onChangeText={setReason} maxLength={300} />
              <Button
                title={t("work.job.decline")}
                variant="destructive"
                loading={busy === "decline"}
                disabled={busy !== null}
                onPress={() => void run("decline", () => artisanApi.decline(id, reason.trim()), t("work.job.declined"))}
              />
            </>
          ) : (
            <Button title={t("work.job.decline")} variant="ghost" disabled={busy !== null} onPress={() => setDeclining(true)} />
          )}
        </Card>
      ) : null}

      {can("start") || can("complete") ? (
        <Card>
          {can("start") ? (
            <Button
              title={t("work.job.start")}
              loading={busy === "start"}
              disabled={busy !== null}
              onPress={() => void run("start", () => artisanApi.start(id), t("work.job.started"))}
            />
          ) : null}
          {completing ? (
            <>
              <TextField
                label={t("work.job.completeLabel")}
                hint={t("work.job.completeHint")}
                value={note}
                onChangeText={setNote}
                multiline
                maxLength={1000}
              />
              <Button
                title={t("work.job.completeSend")}
                loading={busy === "complete"}
                disabled={busy !== null || !note.trim()}
                onPress={() =>
                  void run("complete", () => artisanApi.complete(id, note.trim()), t("work.job.completed")).then((ok) => {
                    if (ok) setCompleting(false);
                  })
                }
              />
            </>
          ) : can("complete") ? (
            <Button title={t("work.job.complete")} variant={can("start") ? "secondary" : "primary"} onPress={() => setCompleting(true)} />
          ) : null}
          {can("photo") ? (
            <View className="gap-2">
              <Text variant="label">{t("work.job.photo")}</Text>
              <PhotoButtons
                disabled={busy !== null}
                onPicked={(p) => void run("photo", () => artisanApi.addPhoto(id, photoForm(p)), t("work.job.photoAdded"))}
                onDenied={() => setError(t("repairs.form.permission"))}
              />
            </View>
          ) : null}
        </Card>
      ) : null}

      {tk.photos.length ? (
        <Card>
          <PhotoGrid photos={tk.photos} />
        </Card>
      ) : null}

      {can("comment") ? (
        <Card>
          <TextField label={t("work.job.comment")} value={comment} onChangeText={setComment} multiline maxLength={1000} />
          <Button
            title={t("work.job.commentSend")}
            variant="secondary"
            loading={busy === "comment"}
            disabled={busy !== null || !comment.trim()}
            onPress={() =>
              void run("comment", () => artisanApi.comment(id, comment.trim()), t("work.job.commented")).then((ok) => {
                if (ok) setComment("");
              })
            }
          />
        </Card>
      ) : null}

      {tk.events.length ? (
        <Card>
          <Timeline events={tk.events} />
        </Card>
      ) : null}
      <Text variant="caption">{t("work.job.noPayment")}</Text>
    </Screen>
  );
}
