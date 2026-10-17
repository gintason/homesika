import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { View } from "react-native";

import { artisanApi, type MyVoucher, type VoucherKind } from "@/api";
import { Banner, Button, Card, PhoneInput, Screen, SkeletonCard, Text, TextField } from "@/components";
import { ToneBadge } from "@/components/repairs";
import { keys, useMyArtisan } from "@/hooks/queries";
import { ApiError, errorText } from "@/lib/api";
import { formatPhone, normalisePhone } from "@/lib/phone";

const TONE = { pending: "warning", confirmed: "success", declined: "neutral", expired: "neutral" } as const;

/** Guarantors and references: each gets an SMS link to confirm (backend apps/artisans/services.py). */
export default function People() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const me = useMyArtisan();
  const [adding, setAdding] = useState<VoucherKind | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  if (!me.data) {
    return (
      <Screen title={t("work.people.title")} back>
        {me.error ? <Banner message={errorText(me.error)} onRetry={() => me.refetch()} retryLabel={t("common.retry")} /> : <SkeletonCard label={t("common.loading")} />}
      </Screen>
    );
  }
  const refresh = () => qc.invalidateQueries({ queryKey: keys.artisan });
  const list = (kind: VoucherKind) => me.data!.vouchers.filter((v) => v.kind === kind);

  const act = async (v: MyVoucher, kind: "resend" | "remove") => {
    setBusyId(`${kind}-${v.id}`);
    setError(null);
    try {
      if (kind === "resend") await artisanApi.resendVoucher(v.id);
      else await artisanApi.removeVoucher(v.id);
      setNotice(kind === "resend" ? t("work.people.resent") : t("work.people.removed"));
      await refresh();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusyId(null);
    }
  };

  const section = (kind: VoucherKind) => (
    <Card>
      <Text variant="heading" accessibilityRole="header">
        {kind === "guarantor" ? t("work.people.guarantors") : t("work.people.references")}
      </Text>
      <Text variant="caption">{kind === "guarantor" ? t("work.people.guarantorsHint") : t("work.people.referencesHint")}</Text>
      {list(kind).map((v) => (
        <View key={v.id} className="gap-2 border-t border-surface-line pt-3">
          <View className="flex-row flex-wrap items-center justify-between gap-2">
            <Text variant="label">{v.full_name}</Text>
            <ToneBadge tone={TONE[v.status]} label={t(`work.people.status.${v.status}`)} />
          </View>
          <Text variant="caption">
            {formatPhone(v.phone_number)} · {v.relationship}
          </Text>
          {v.status === "pending" || v.status === "expired" ? (
            <View className="flex-row flex-wrap gap-2">
              <Button
                title={t("work.people.resend")}
                variant="secondary"
                loading={busyId === `resend-${v.id}`}
                disabled={busyId !== null}
                onPress={() => void act(v, "resend")}
              />
              <Button
                title={t("work.people.remove", { name: v.full_name })}
                variant="ghost"
                loading={busyId === `remove-${v.id}`}
                disabled={busyId !== null}
                onPress={() => void act(v, "remove")}
              />
            </View>
          ) : null}
        </View>
      ))}
      {adding === kind ? (
        <AddForm
          kind={kind}
          onDone={(name) => {
            setAdding(null);
            setNotice(t("work.people.added", { name }));
            void refresh();
          }}
          onCancel={() => setAdding(null)}
        />
      ) : (
        <Button
          title={t("work.people.add", { kind: t(`work.people.kind.${kind}`) })}
          variant="secondary"
          onPress={() => {
            setNotice(null);
            setAdding(kind);
          }}
        />
      )}
    </Card>
  );

  return (
    <Screen title={t("work.people.title")} back onRefresh={() => me.refetch()} refreshing={me.isRefetching}>
      {notice ? <Banner tone="success" message={notice} /> : null}
      {error ? <Banner message={error} /> : null}
      <Text>{t("work.people.intro")}</Text>
      {section("guarantor")}
      {section("reference")}
    </Screen>
  );
}

function AddForm({ kind, onDone, onCancel }: { kind: VoucherKind; onDone: (name: string) => void; onCancel: () => void }) {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [relationship, setRelationship] = useState("");
  const [occupation, setOccupation] = useState("");
  const [address, setAddress] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});

  const save = async () => {
    setBusy(true);
    setError(null);
    setFields({});
    try {
      await artisanApi.addVoucher({
        kind,
        full_name: name.trim(),
        phone_number: normalisePhone(phone),
        relationship: relationship.trim(),
        occupation: occupation.trim(),
        address: address.trim(),
      });
      onDone(name.trim());
    } catch (e) {
      if (e instanceof ApiError) setFields(Object.fromEntries(Object.keys(e.details).map((k) => [k, e.fieldMessage(k) ?? ""])));
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <View className="gap-3 border-t border-surface-line pt-3">
      {error ? <Banner message={error} /> : null}
      <TextField label={t("work.people.name")} value={name} onChangeText={setName} maxLength={120} error={fields.full_name} />
      <PhoneInput label={t("work.people.phone")} value={phone} onChangeText={setPhone} error={fields.phone_number} />
      <TextField
        label={t("work.people.relationship")}
        hint={t("work.people.relationshipHint")}
        value={relationship}
        onChangeText={setRelationship}
        maxLength={80}
        error={fields.relationship}
      />
      <TextField label={t("work.people.occupation")} value={occupation} onChangeText={setOccupation} maxLength={80} />
      {kind === "guarantor" ? (
        <TextField label={t("work.people.address")} value={address} onChangeText={setAddress} maxLength={255} error={fields.address} />
      ) : null}
      <Button
        title={t("work.people.save")}
        loading={busy}
        disabled={!name.trim() || !phone.trim() || !relationship.trim()}
        onPress={() => void save()}
      />
      <Button title={t("common.cancel")} variant="ghost" onPress={onCancel} />
    </View>
  );
}
