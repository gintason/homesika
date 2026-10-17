import { useQueryClient } from "@tanstack/react-query";
import { router } from "expo-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { estatesApi } from "@/api";
import { Banner, Button, Screen, Text, TextField } from "@/components";
import { keys } from "@/hooks/queries";
import { ApiError, errorText } from "@/lib/api";

/** Join with the estate's code and my house; the estate office then approves me. */
export default function JoinEstate() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [code, setCode] = useState("");
  const [house, setHouse] = useState("");
  const [errors, setErrors] = useState<{ code?: string; house?: string }>({});
  const [banner, setBanner] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    const e: typeof errors = {};
    if (code.trim().length < 6) e.code = t("estate.codeHint");
    if (!house.trim()) e.house = t("estate.houseHint");
    setErrors(e);
    if (Object.keys(e).length) return;
    setBusy(true);
    setBanner(null);
    try {
      await estatesApi.join(code.trim().toUpperCase(), house.trim());
      await qc.invalidateQueries({ queryKey: keys.estates });
      router.replace("/estate");
    } catch (err) {
      if (err instanceof ApiError && err.fieldMessage("house")) setErrors({ house: err.fieldMessage("house") });
      else setBanner(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen title={t("estate.joinTitle")} back footer={<Button title={t("estate.joinButton")} loading={busy} onPress={() => void submit()} />}>
      <Text>{t("estate.joinBody")}</Text>
      {banner ? <Banner message={banner} /> : null}
      <TextField
        label={t("estate.code")}
        hint={t("estate.codeHint")}
        error={errors.code}
        value={code}
        autoCapitalize="characters"
        autoCorrect={false}
        maxLength={8}
        onChangeText={(v) => setCode(v.replace(/[^A-Za-z0-9]/g, ""))}
      />
      <TextField label={t("estate.house")} hint={t("estate.houseHint")} error={errors.house} value={house} maxLength={60} onChangeText={setHouse} />
    </Screen>
  );
}
