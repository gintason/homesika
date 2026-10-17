import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Image, View } from "react-native";

import { artisanApi, ID_TYPES, type IdType } from "@/api";
import { Banner, Button, Screen, SkeletonCard, Text, TextField } from "@/components";
import { ChoiceChips } from "@/components/bills";
import { PhotoButtons } from "@/components/repairs";
import { keys, useMyArtisan } from "@/hooks/queries";
import { ApiError, errorText } from "@/lib/api";
import { photoForm, type PhotoFile } from "@/lib/photos";
import { parseDob } from "@/lib/repairs";

/**
 * POST /artisans/me/verification/id/ (multipart).
 * "nin" mode (default): NIN + date of birth + a photo of the NIN slip or card. Looked up with a licensed
 * provider and read automatically; the screen follows the result (processing -> passed / failed /
 * a person reviewing) and offers "Ask a person to review" after an automatic failure.
 * "manual" mode: any ID type; Homesika staff review it.
 */
export default function IdCheck() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const me = useMyArtisan();
  const [type, setType] = useState<IdType>("nin");
  const [number, setNumber] = useState("");
  const [dob, setDob] = useState("");
  const [photo, setPhoto] = useState<PhotoFile | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [retrying, setRetrying] = useState(false);

  if (!me.data) {
    return (
      <Screen title={t("work.id.title")} back>
        {me.error ? <Banner message={errorText(me.error)} onRetry={() => me.refetch()} retryLabel={t("common.retry")} /> : <SkeletonCard label={t("common.loading")} />}
      </Screen>
    );
  }
  const nin = (me.data.verification_mode ?? "manual") === "nin";
  const check = me.data.checks.find((c) => c.kind === "id");
  const status = check?.status ?? "not_started";

  const submit = async () => {
    const e: Record<string, string> = {};
    const isoDob = nin ? parseDob(dob) : "";
    if (nin && !isoDob) e.date_of_birth = t("work.id.dobInvalid");
    if (!photo) e.document = t("work.id.photoHint");
    setFields(e);
    if (Object.keys(e).length) return;
    setBusy(true);
    setError(null);
    try {
      const extra: Record<string, string> = { id_type: nin ? "nin" : type, id_number: number };
      if (nin) extra.date_of_birth = isoDob!;
      qc.setQueryData(keys.artisan, await artisanApi.submitId(photoForm(photo!, "document", extra)));
      setRetrying(false);
    } catch (err) {
      if (err instanceof ApiError) setFields(Object.fromEntries(Object.keys(err.details).map((k) => [k, err.fieldMessage(k) ?? ""])));
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  const askPerson = async () => {
    setBusy(true);
    setError(null);
    try {
      qc.setQueryData(keys.artisan, await artisanApi.requestReview("id"));
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  const showForm = status === "not_started" || (status === "failed" && retrying) || (status === "failed" && !check?.can_request_review);
  if (!showForm) {
    return (
      <Screen title={t("work.id.title")} back onRefresh={() => me.refetch()} refreshing={me.isRefetching}>
        {error ? <Banner message={error} /> : null}
        {status === "processing" ? <Banner tone="info" message={t("work.id.processing")} /> : null}
        {status === "passed" ? <Banner tone="success" message={t("work.id.passed")} /> : null}
        {status === "pending" ? <Banner tone="info" message={check?.review_requested_at ? t("work.id.reviewSent") : check?.note || t("work.id.pending")} /> : null}
        {status === "failed" ? (
          <>
            <Banner message={t("work.id.failed", { note: check?.note ?? "" })} />
            <Button title={t("work.id.tryAgain")} onPress={() => setRetrying(true)} />
            <Button title={t("work.id.review")} variant="secondary" loading={busy} onPress={() => void askPerson()} />
          </>
        ) : null}
      </Screen>
    );
  }

  return (
    <Screen
      title={t("work.id.title")}
      back
      footer={<Button title={t("work.id.submit")} loading={busy} disabled={!number.trim()} onPress={() => void submit()} />}
    >
      {status === "failed" ? <Banner message={t("work.id.failed", { note: check?.note ?? "" })} /> : null}
      {error ? <Banner message={error} /> : null}
      <Text>{nin ? t("work.id.ninIntro") : t("work.id.intro")}</Text>
      {nin ? null : (
        <ChoiceChips
          label={t("work.id.type")}
          value={type}
          onChange={(v) => setType(v as IdType)}
          choices={ID_TYPES.map((x) => ({ value: x, label: t(`work.id.types.${x}`) }))}
        />
      )}
      <TextField
        label={nin ? t("work.id.nin") : t("work.id.number")}
        hint={nin || type === "nin" ? t("work.id.ninHint") : undefined}
        value={number}
        onChangeText={setNumber}
        keyboardType={nin || type === "nin" ? "number-pad" : "default"}
        autoCapitalize="characters"
        maxLength={30}
        error={fields.id_number}
      />
      {nin ? (
        <TextField
          label={t("work.id.dob")}
          hint={t("work.id.dobHint")}
          placeholder="DD/MM/YYYY"
          value={dob}
          onChangeText={setDob}
          keyboardType="numbers-and-punctuation"
          maxLength={10}
          error={fields.date_of_birth}
        />
      ) : null}
      <View className="gap-2">
        <Text variant="label">{nin ? t("work.id.ninPhoto") : t("work.id.photo")}</Text>
        <Text variant="caption">{t("work.id.photoHint")}</Text>
        {photo ? <Image source={{ uri: photo.uri }} className="h-40 w-full rounded-md bg-surface-muted" resizeMode="contain" accessibilityLabel={t("work.id.photo")} /> : null}
        <PhotoButtons
          cameraLabel={photo ? t("work.id.retake") : t("work.id.takePhoto")}
          galleryLabel={t("work.id.choosePhoto")}
          onPicked={setPhoto}
          onDenied={() => setError(t("repairs.form.permission"))}
        />
        {fields.document ? <Text className="text-danger-700">{fields.document}</Text> : null}
      </View>
    </Screen>
  );
}
