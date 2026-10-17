import { useQueryClient } from "@tanstack/react-query";
import { router, useLocalSearchParams } from "expo-router";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Share, View } from "react-native";

import { estatesApi, type GatePass, type GatePassInput } from "@/api";
import { Banner, Button, Card, PhoneInput, Screen, Text, TextField } from "@/components";
import { ChoiceChips } from "@/components/bills";
import { keys } from "@/hooks/queries";
import { ApiError, errorText } from "@/lib/api";
import { formatDateTime } from "@/lib/date";
import { newIdempotencyKey } from "@/lib/idempotency";
import { formatPhone, isValidPhone, normalisePhone } from "@/lib/phone";

const HOURS = [4, 12, 24, 72];
const ENTRIES = [1, 2, 5];

/** A gate pass for a visitor: the code is shown here and texted to them if a phone is given. */
export default function NewGatePass() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const { estate = "" } = useLocalSearchParams<{ estate: string }>();
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [kind, setKind] = useState<GatePass["kind"]>("visitor");
  const [hours, setHours] = useState(12);
  const [entries, setEntries] = useState(1);
  const [note, setNote] = useState("");
  const [errors, setErrors] = useState<{ name?: string; phone?: string }>({});
  const [banner, setBanner] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<GatePass | null>(null);
  const last = useRef<{ signature: string; key: string } | null>(null);

  if (done) {
    const until = formatDateTime(done.valid_to);
    return (
      <Screen title={t("estate.passes.created")} back>
        <Card accessible accessibilityLabel={`${t("estate.passes.code")} ${done.code.split("").join(" ")}`}>
          <Text variant="caption">{t("estate.passes.code")}</Text>
          <Text variant="display" className="tracking-widest">
            {done.code}
          </Text>
          <Text>{done.visitor_name}</Text>
          <Text className="text-ink-600">{t("estate.passes.until", { time: until })}</Text>
          {done.visitor_phone ? <Text className="text-ink-600">{t("estate.passes.texted", { phone: formatPhone(done.visitor_phone) })}</Text> : null}
        </Card>
        <Button
          title={t("estate.passes.share")}
          onPress={() =>
            void Share.share({ message: t("estate.passes.shareMessage", { estate: done.estate_name, code: done.code, time: until }) }).catch(() => {})
          }
        />
        <Button title={t("common.done")} variant="ghost" onPress={() => router.back()} />
      </Screen>
    );
  }

  const submit = async () => {
    const e: typeof errors = {};
    if (name.trim().length < 2) e.name = t("estate.passes.visitor");
    if (phone && !isValidPhone(normalisePhone(phone))) e.phone = t("auth.phoneInvalid");
    setErrors(e);
    if (Object.keys(e).length || busy) return;
    const input: GatePassInput = {
      estate,
      visitor_name: name.trim(),
      visitor_phone: phone ? normalisePhone(phone) : "",
      kind,
      hours,
      max_uses: entries,
      note: note.trim(),
    };
    const signature = JSON.stringify(input);
    const key = last.current?.signature === signature ? last.current.key : newIdempotencyKey("pass");
    last.current = { signature, key };
    setBusy(true);
    setBanner(null);
    try {
      const gp = await estatesApi.createPass(input, key);
      await qc.invalidateQueries({ queryKey: keys.passes });
      setDone(gp);
    } catch (err) {
      if (err instanceof ApiError && err.fieldMessage("visitor_phone")) setErrors({ phone: err.fieldMessage("visitor_phone") });
      else setBanner(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen title={t("estate.passes.new")} back footer={<Button title={t("estate.passes.create")} loading={busy} onPress={() => void submit()} />}>
      {banner ? <Banner message={banner} /> : null}
      <TextField label={t("estate.passes.visitor")} error={errors.name} value={name} maxLength={120} onChangeText={setName} />
      <PhoneInput label={t("estate.passes.phone")} hint={t("estate.passes.phoneHint")} error={errors.phone} value={phone} onChangeText={setPhone} />
      <ChoiceChips
        label={t("estate.passes.kind")}
        value={kind}
        onChange={(v) => setKind(v as GatePass["kind"])}
        choices={(["visitor", "delivery", "artisan"] as const).map((k) => ({ value: k, label: t(`estate.passes.kinds.${k}`) }))}
      />
      <ChoiceChips
        label={t("estate.passes.hours")}
        value={String(hours)}
        onChange={(v) => setHours(Number(v))}
        choices={HOURS.map((h) => ({ value: String(h), label: t("estate.passes.hoursValue", { count: h }) }))}
      />
      <ChoiceChips
        label={t("estate.passes.entries")}
        value={String(entries)}
        onChange={(v) => setEntries(Number(v))}
        choices={ENTRIES.map((n) => ({ value: String(n), label: t("estate.passes.entriesValue", { count: n }) }))}
      />
      <View>
        <TextField label={`${t("estate.passes.note")} (${t("common.optional")})`} value={note} maxLength={200} onChangeText={setNote} />
      </View>
    </Screen>
  );
}
