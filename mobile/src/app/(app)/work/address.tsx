import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Image, View } from "react-native";

import { artisanApi } from "@/api";
import { Banner, Button, Card, Screen, SkeletonCard, Text } from "@/components";
import { PhotoButtons } from "@/components/repairs";
import { keys, useMyArtisan } from "@/hooks/queries";
import { errorText } from "@/lib/api";
import { photoForm, type PhotoFile } from "@/lib/photos";

/** Proof of address (POST /artisans/me/verification/address/), read automatically. */
export default function AddressCheck() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const me = useMyArtisan();
  const [photo, setPhoto] = useState<PhotoFile | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);

  if (!me.data) {
    return (
      <Screen title={t("work.address.title")} back>
        {me.error ? <Banner message={errorText(me.error)} onRetry={() => me.refetch()} retryLabel={t("common.retry")} /> : <SkeletonCard label={t("common.loading")} />}
      </Screen>
    );
  }
  const profile = me.data;
  const check = profile.checks.find((c) => c.kind === "address");
  const status = check?.status ?? "not_started";
  const address = [profile.address, profile.city, profile.state].filter(Boolean).join(", ");

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      qc.setQueryData(keys.artisan, await fn());
      setRetrying(false);
      setPhoto(null);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  if ((profile.verification_mode ?? "manual") !== "nin") {
    return (
      <Screen title={t("work.address.title")} back>
        <Banner tone="info" message={t("work.address.staff")} />
      </Screen>
    );
  }

  const showForm = status === "not_started" || (status === "failed" && (retrying || !check?.can_request_review));
  return (
    <Screen
      title={t("work.address.title")}
      back
      onRefresh={() => me.refetch()}
      refreshing={me.isRefetching}
      footer={
        showForm ? (
          <Button
            title={t("work.address.submit")}
            loading={busy}
            disabled={!photo}
            onPress={() => void run(() => artisanApi.submitAddressProof(photoForm(photo!, "document")))}
          />
        ) : undefined
      }
    >
      {error ? <Banner message={error} /> : null}
      {status === "processing" ? <Banner tone="info" message={t("work.address.processing")} /> : null}
      {status === "passed" ? <Banner tone="success" message={t("work.address.passed")} /> : null}
      {status === "pending" ? <Banner tone="info" message={check?.review_requested_at ? t("work.id.reviewSent") : t("work.address.pending")} /> : null}
      {status === "failed" ? <Banner message={t("work.address.failed", { note: check?.note ?? "" })} /> : null}
      {status === "failed" && !showForm ? (
        <>
          <Button title={t("work.id.tryAgain")} onPress={() => setRetrying(true)} />
          <Button title={t("work.id.review")} variant="secondary" loading={busy} onPress={() => void run(() => artisanApi.requestReview("address"))} />
        </>
      ) : null}
      {showForm ? (
        <>
          <Text>{t("work.address.intro")}</Text>
          <Card>
            <Text variant="label">{t("work.address.yours", { address })}</Text>
          </Card>
          <View className="gap-2">
            <Text variant="label">{t("work.address.photo")}</Text>
            {photo ? <Image source={{ uri: photo.uri }} className="h-40 w-full rounded-md bg-surface-muted" resizeMode="contain" accessibilityLabel={t("work.address.photo")} /> : null}
            <PhotoButtons
              cameraLabel={t("work.address.takePhoto")}
              galleryLabel={t("work.address.choosePhoto")}
              onPicked={setPhoto}
              onDenied={() => setError(t("repairs.form.permission"))}
            />
          </View>
        </>
      ) : null}
    </Screen>
  );
}
