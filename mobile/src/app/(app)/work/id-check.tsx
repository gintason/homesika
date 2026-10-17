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

/** POST /artisans/me/verification/id/ (multipart): ID type, number and a photo for Homesika to check. */
export default function IdCheck() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const me = useMyArtisan();
  const [type, setType] = useState<IdType>("nin");
  const [number, setNumber] = useState("");
  const [photo, setPhoto] = useState<PhotoFile | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [sent, setSent] = useState(false);

  const check = me.data?.checks.find((c) => c.kind === "id");
  if (!me.data) {
    return (
      <Screen title={t("work.id.title")} back>
        {me.error ? <Banner message={errorText(me.error)} onRetry={() => me.refetch()} retryLabel={t("common.retry")} /> : <SkeletonCard label={t("common.loading")} />}
      </Screen>
    );
  }
  const done = check?.status === "passed";
  const waiting = check?.status === "pending";

  const submit = async () => {
    if (!photo) {
      setFields({ document: t("work.id.photoHint") });
      return;
    }
    setBusy(true);
    setError(null);
    setFields({});
    try {
      const profile = await artisanApi.submitId(photoForm(photo, "document", { id_type: type, id_number: number }));
      qc.setQueryData(keys.artisan, profile);
      setSent(true);
    } catch (e) {
      if (e instanceof ApiError) setFields(Object.fromEntries(Object.keys(e.details).map((k) => [k, e.fieldMessage(k) ?? ""])));
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  if (done || waiting || sent) {
    return (
      <Screen title={t("work.id.title")} back>
        <Banner tone={done ? "success" : "info"} message={done ? t("work.id.passed") : sent ? t("work.id.sent") : t("work.id.pending")} />
      </Screen>
    );
  }

  return (
    <Screen
      title={t("work.id.title")}
      back
      footer={<Button title={t("work.id.submit")} loading={busy} disabled={!number.trim()} onPress={() => void submit()} />}
    >
      {check?.status === "failed" ? <Banner message={t("work.id.failed", { note: check.note })} /> : null}
      {error ? <Banner message={error} /> : null}
      <Text>{t("work.id.intro")}</Text>
      <ChoiceChips
        label={t("work.id.type")}
        value={type}
        onChange={(v) => setType(v as IdType)}
        choices={ID_TYPES.map((x) => ({ value: x, label: t(`work.id.types.${x}`) }))}
      />
      <TextField
        label={t("work.id.number")}
        hint={type === "nin" ? t("work.id.ninHint") : undefined}
        value={number}
        onChangeText={setNumber}
        keyboardType={type === "nin" ? "number-pad" : "default"}
        autoCapitalize="characters"
        maxLength={30}
        error={fields.id_number}
      />
      <View className="gap-2">
        <Text variant="label">{t("work.id.photo")}</Text>
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
