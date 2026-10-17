import { router } from "expo-router";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Image, Linking, Pressable, View } from "react-native";

import { repairsApi, TRADES, type ReportInput, type TicketPriority, type Trade } from "@/api";
import { Banner, Button, Card, EmptyState, Screen, SkeletonCard, Text, TextField } from "@/components";
import { ChoiceChips } from "@/components/bills";
import { PhotoButtons } from "@/components/repairs";
import { keys, useLeases } from "@/hooks/queries";
import { ApiError, errorText } from "@/lib/api";
import { newIdempotencyKey } from "@/lib/idempotency";
import { photoForm, type PhotoFile } from "@/lib/photos";
import { useQueryClient } from "@tanstack/react-query";

const MAX_PHOTOS = 6;
const PRIORITIES: TicketPriority[] = ["normal", "urgent", "emergency", "low"];

/**
 * Report a problem: home, what, how urgent, a description and photos.
 * POST /me/tickets/ (one Idempotency-Key per submission, reused on retry) then each photo to
 * /me/tickets/{id}/photos/. A photo that fails doesn't lose the request: it can be added from the detail.
 */
export default function ReportRepair() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const leases = useLeases();
  const active = (leases.data ?? []).filter((l) => l.status === "active");
  const [lease, setLease] = useState<string | null>(null);
  const [category, setCategory] = useState<Trade | null>(null);
  const [priority, setPriority] = useState<TicketPriority>("normal");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [access, setAccess] = useState("");
  const [photos, setPhotos] = useState<PhotoFile[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [banner, setBanner] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const last = useRef<{ signature: string; key: string } | null>(null);
  const leaseId = lease ?? (active.length === 1 ? active[0]!.id : null);

  if (leases.isPending) {
    return (
      <Screen title={t("repairs.form.title")} back>
        <SkeletonCard label={t("common.loading")} />
      </Screen>
    );
  }
  if (!active.length) {
    return (
      <Screen title={t("repairs.form.title")} back>
        <EmptyState icon="home-outline" title={t("repairs.title")} body={t("repairs.noLease")} />
      </Screen>
    );
  }

  const validate = (): ReportInput | null => {
    const e: Record<string, string> = {};
    if (!leaseId) e.lease = t("repairs.form.chooseHome");
    if (!category) e.category = t("repairs.form.chooseCategory");
    if (title.trim().length < 3) e.title = t("repairs.form.needTitle");
    if (description.trim().length < 10) e.description = t("repairs.form.needDescription");
    setErrors(e);
    if (Object.keys(e).length) return null;
    return {
      lease: leaseId!,
      category: category!,
      priority,
      title: title.trim(),
      description: description.trim(),
      access_notes: access.trim(),
    };
  };

  const submit = async () => {
    const input = validate();
    if (!input || busy) return;
    const signature = JSON.stringify(input);
    const key = last.current?.signature === signature ? last.current.key : newIdempotencyKey("ticket");
    last.current = { signature, key };
    setBanner(null);
    setBusy(t("repairs.form.sending"));
    try {
      const ticket = await repairsApi.report(input, key);
      last.current = null;
      let failed = 0;
      for (const [i, photo] of photos.entries()) {
        setBusy(t("repairs.form.uploading", { n: i + 1, total: photos.length }));
        try {
          await repairsApi.addPhoto(ticket.id, photoForm(photo));
        } catch {
          failed += 1;
        }
      }
      void qc.invalidateQueries({ queryKey: keys.tickets });
      router.replace({ pathname: "/repairs/[id]", params: { id: ticket.id, ...(failed ? { photosFailed: String(failed) } : {}) } });
    } catch (e) {
      if (e instanceof ApiError && e.code === "validation_error") {
        setErrors(Object.fromEntries(Object.keys(e.details).map((k) => [k, e.fieldMessage(k) ?? ""])));
      }
      setBanner(errorText(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <Screen
      title={t("repairs.form.title")}
      back
      footer={<Button title={t("repairs.form.send")} loading={busy !== null} loadingLabel={busy ?? undefined} onPress={() => void submit()} />}
    >
      {banner ? <Banner message={banner} /> : null}
      {active.length > 1 ? (
        <View className="gap-1">
          <ChoiceChips
            label={t("repairs.form.home")}
            value={leaseId}
            onChange={setLease}
            choices={active.map((l) => ({ value: l.id, label: `${l.unit_label}, ${l.property_name}` }))}
          />
          {errors.lease ? <Text className="text-danger-700">{errors.lease}</Text> : null}
        </View>
      ) : null}

      <View className="gap-1">
        <ChoiceChips
          label={t("repairs.form.what")}
          value={category}
          onChange={(v) => setCategory(v as Trade)}
          choices={TRADES.map((c) => ({ value: c, label: t(`repairs.category.${c}`) }))}
        />
        {errors.category ? <Text className="text-danger-700">{errors.category}</Text> : null}
      </View>

      <View className="gap-2">
        <ChoiceChips
          label={t("repairs.form.how")}
          value={priority}
          onChange={(v) => setPriority(v as TicketPriority)}
          choices={PRIORITIES.map((p) => ({ value: p, label: t(`repairs.priority.${p}`) }))}
        />
        <Text variant="caption">{t(`repairs.priorityHint.${priority}`)}</Text>
        {priority === "emergency" ? (
          <Card>
            <Text>{t("repairs.form.emergency")}</Text>
            <Button title={t("repairs.form.call112")} variant="secondary" onPress={() => void Linking.openURL("tel:112")} />
          </Card>
        ) : null}
      </View>

      <TextField
        label={t("repairs.form.titleLabel")}
        hint={t("repairs.form.titleHint")}
        placeholder={t("repairs.form.titleHint")}
        value={title}
        onChangeText={setTitle}
        maxLength={120}
        error={errors.title}
      />
      <TextField
        label={t("repairs.form.description")}
        hint={t("repairs.form.descriptionHint")}
        value={description}
        onChangeText={setDescription}
        maxLength={2000}
        multiline
        error={errors.description}
      />
      <TextField
        label={t("repairs.form.access")}
        hint={t("repairs.form.accessHint")}
        placeholder={t("repairs.form.accessHint")}
        value={access}
        onChangeText={setAccess}
        maxLength={200}
      />

      <View className="gap-2">
        <Text variant="label">{t("repairs.form.photos")}</Text>
        <Text variant="caption">{t("repairs.form.photosHint", { max: MAX_PHOTOS })}</Text>
        {photos.length ? (
          <View className="flex-row flex-wrap gap-2">
            {photos.map((p, i) => (
              <Pressable
                key={`${p.uri}-${i}`}
                onPress={() => setPhotos((all) => all.filter((_, j) => j !== i))}
                accessibilityRole="button"
                accessibilityLabel={t("repairs.form.removePhoto", { n: i + 1 })}
              >
                <Image source={{ uri: p.uri }} className="h-24 w-24 rounded-md bg-surface-muted" accessibilityIgnoresInvertColors />
              </Pressable>
            ))}
          </View>
        ) : null}
        {photos.length < MAX_PHOTOS ? (
          <PhotoButtons
            disabled={busy !== null}
            onPicked={(p) => setPhotos((all) => [...all, p].slice(0, MAX_PHOTOS))}
            onDenied={() => setBanner(t("repairs.form.permission"))}
          />
        ) : null}
      </View>
    </Screen>
  );
}
