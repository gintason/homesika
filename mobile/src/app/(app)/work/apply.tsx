import { useQueryClient } from "@tanstack/react-query";
import { router } from "expo-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Pressable, View } from "react-native";

import { artisanApi, TRADES, type Trade } from "@/api";
import { Banner, Button, Checkbox, Screen, Text, TextField } from "@/components";
import { keys } from "@/hooks/queries";
import { ApiError, errorText } from "@/lib/api";

/** Pick several trades: each pill is a checkbox (48 tall, label always visible). */
function TradePicker({ value, onChange, label }: { value: Trade[]; onChange: (v: Trade[]) => void; label: string }) {
  const { t } = useTranslation();
  return (
    <View className="gap-2">
      <Text variant="label">{label}</Text>
      <View className="flex-row flex-wrap gap-2">
        {TRADES.map((trade) => {
          const on = value.includes(trade);
          return (
            <Pressable
              key={trade}
              onPress={() => onChange(on ? value.filter((x) => x !== trade) : [...value, trade])}
              accessibilityRole="checkbox"
              accessibilityState={{ checked: on }}
              accessibilityLabel={t(`repairs.category.${trade}`)}
              className={`min-h-12 items-center justify-center rounded-pill border-2 px-4 py-2 ${on ? "border-primary-600 bg-primary-600" : "border-ink-400 bg-white"}`}
            >
              <Text variant="label" className={on ? "text-white" : "text-ink-800"}>
                {t(`repairs.category.${trade}`)}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

/** POST /artisans/apply/: who they are, what they do, where, and consent to the checks (NDPA). */
export default function ApplyAsArtisan() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [trades, setTrades] = useState<Trade[]>([]);
  const [areas, setAreas] = useState("");
  const [address, setAddress] = useState("");
  const [city, setCity] = useState("");
  const [state, setState] = useState("");
  const [years, setYears] = useState("");
  const [bio, setBio] = useState("");
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});

  const submit = async () => {
    if (!consent) {
      setError(t("work.apply.consentNeeded"));
      return;
    }
    setBusy(true);
    setError(null);
    setFields({});
    try {
      const profile = await artisanApi.apply({
        display_name: name.trim(),
        trades,
        service_areas: areas
          .split(",")
          .map((a) => a.trim())
          .filter(Boolean),
        address: address.trim(),
        city: city.trim(),
        state: state.trim(),
        bio: bio.trim(),
        years_experience: /^\d+$/.test(years.trim()) ? Number(years.trim()) : null,
        consent,
      });
      qc.setQueryData(keys.artisan, profile);
      router.replace("/work");
    } catch (e) {
      if (e instanceof ApiError) setFields(Object.fromEntries(Object.keys(e.details).map((k) => [k, e.fieldMessage(k) ?? ""])));
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen title={t("work.apply.title")} back footer={<Button title={t("work.apply.submit")} loading={busy} onPress={() => void submit()} />}>
      {error ? <Banner message={error} /> : null}
      <TextField label={t("work.apply.name")} hint={t("work.apply.nameHint")} value={name} onChangeText={setName} maxLength={120} error={fields.display_name} />
      <TradePicker label={t("work.apply.trades")} value={trades} onChange={setTrades} />
      {fields.trades ? <Text className="text-danger-700">{fields.trades}</Text> : null}
      <TextField label={t("work.apply.areas")} hint={t("work.apply.areasHint")} value={areas} onChangeText={setAreas} error={fields.service_areas} />
      <TextField
        label={t("work.apply.address")}
        hint={t("work.apply.addressHint")}
        value={address}
        onChangeText={setAddress}
        maxLength={255}
        error={fields.address}
      />
      <View className="flex-row gap-3">
        <View className="flex-1">
          <TextField label={t("work.apply.city")} value={city} onChangeText={setCity} maxLength={80} />
        </View>
        <View className="flex-1">
          <TextField label={t("work.apply.state")} value={state} onChangeText={setState} maxLength={80} />
        </View>
      </View>
      <TextField label={t("work.apply.years")} value={years} onChangeText={setYears} keyboardType="number-pad" maxLength={2} />
      <TextField label={t("work.apply.bio")} value={bio} onChangeText={setBio} multiline maxLength={300} />
      <Checkbox checked={consent} onChange={setConsent} label={t("work.apply.consent")}>
        <Text className="flex-1">{t("work.apply.consent")}</Text>
      </Checkbox>
    </Screen>
  );
}
