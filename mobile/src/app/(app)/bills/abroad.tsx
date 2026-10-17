import { useQuery } from "@tanstack/react-query";
import { router } from "expo-router";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { View } from "react-native";

import { billsApi, type IntlLookup } from "@/api";
import { Banner, Button, Card, Screen, SkeletonCard, Text, TextField } from "@/components";
import { ChoiceChips, SummaryRow } from "@/components/bills";
import { openCheckout } from "@/hooks/useBillCheckout";
import { ApiError, errorText } from "@/lib/api";
import { newIdempotencyKey } from "@/lib/idempotency";
import { formatMoney, toKobo } from "@/lib/money";

/**
 * Airtime to a phone abroad (Reloadly). The server finds the network from the number and checks the
 * amount; we show an estimate of what arrives, clearly marked as one.
 */
export default function AirtimeAbroad() {
  const { t } = useTranslation();
  const countries = useQuery({ queryKey: ["bills", "intl", "countries"], queryFn: billsApi.intlCountries, retry: false });
  const [country, setCountry] = useState<string | null>(null);
  const [phone, setPhone] = useState("");
  const [lookup, setLookup] = useState<IntlLookup | null>(null);
  const [amount, setAmount] = useState("");
  const [errors, setErrors] = useState<{ phone?: string; amount?: string }>({});
  const [banner, setBanner] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const last = useRef<{ signature: string; key: string } | null>(null);

  if (countries.isPending) {
    return (
      <Screen title={t("bills.intl.title")} back>
        <SkeletonCard label={t("common.loading")} />
      </Screen>
    );
  }
  if (!countries.data) {
    return (
      <Screen title={t("bills.intl.title")} back>
        <Banner message={countries.error instanceof ApiError && countries.error.status === 503 ? t("bills.intl.unavailable") : errorText(countries.error)} />
      </Screen>
    );
  }
  const chosen = countries.data.find((c) => c.code === country) ?? null;
  const op = lookup?.operator;

  const find = async () => {
    if (!chosen) return;
    setBusy(true);
    setErrors({});
    setBanner(null);
    try {
      const r = await billsApi.intlLookup(chosen.code, phone);
      setLookup(r);
      setAmount(r.operator.denomination === "fixed" ? (r.operator.fixed_amounts[0] ?? "") : "");
    } catch (err) {
      if (err instanceof ApiError && err.fieldMessage("phone")) setErrors({ phone: err.fieldMessage("phone") });
      else setBanner(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  const pay = async () => {
    if (!chosen || !lookup) return;
    const input = { country: chosen.code, phone: lookup.phone, amount: amount.replace(/,/g, "") };
    const signature = JSON.stringify(input);
    const key = last.current?.signature === signature ? last.current.key : newIdempotencyKey("intl");
    last.current = { signature, key };
    setBusy(true);
    setErrors({});
    setBanner(null);
    try {
      const order = await billsApi.intlOrder(input, key);
      last.current = null;
      if (order.checkout_url) await openCheckout(order.checkout_url);
      router.replace({ pathname: "/bills/order/[id]", params: { id: order.id } });
    } catch (err) {
      if (err instanceof ApiError && err.fieldMessage("amount")) setErrors({ amount: err.fieldMessage("amount") });
      else setBanner(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  let estimate: string | null = null;
  try {
    if (op?.fx_rate && amount) estimate = ((toKobo(amount.replace(/,/g, "")) / 100) * op.fx_rate).toFixed(2);
  } catch {
    estimate = null;
  }

  return (
    <Screen
      title={t("bills.intl.title")}
      back
      footer={
        lookup ? (
          <Button
            title={amount ? t("bills.pay", { amount: formatMoney(amount.replace(/,/g, "")) }) : t("bills.intl.continue")}
            loading={busy}
            disabled={!amount}
            onPress={() => void pay()}
          />
        ) : (
          <Button title={t("bills.intl.find")} loading={busy} disabled={!chosen || phone.length < 6} onPress={() => void find()} />
        )
      }
    >
      <Text>{t("bills.intl.intro")}</Text>
      {banner ? <Banner message={banner} /> : null}
      <ChoiceChips
        label={t("bills.intl.country")}
        value={country}
        onChange={(v) => {
          setCountry(v);
          setLookup(null);
        }}
        choices={countries.data.map((c) => ({ value: c.code, label: c.name }))}
      />
      {chosen ? (
        <TextField
          label={t("bills.intl.phone")}
          hint={t("bills.intl.phoneHint", { code: chosen.calling_code })}
          keyboardType="phone-pad"
          value={phone}
          error={errors.phone}
          onChangeText={(v) => {
            setPhone(v.replace(/[^\d+ ]/g, ""));
            setLookup(null);
          }}
        />
      ) : null}
      {op ? (
        <Card>
          <SummaryRow label={t("bills.intl.phone")} value={lookup!.phone} />
          <Text variant="label">{t("bills.intl.network", { name: op.name })}</Text>
          {op.sample ? <Banner tone="info" message={t("bills.intl.sample")} /> : null}
          {op.denomination === "fixed" ? (
            <ChoiceChips
              label={t("bills.intl.amount")}
              value={amount}
              onChange={setAmount}
              choices={op.fixed_amounts.map((a) => ({ value: a, label: formatMoney(a) }))}
            />
          ) : (
            <View className="gap-1">
              <TextField
                label={t("bills.intl.amount")}
                hint={t("bills.intl.range", { min: Number(op.min_amount).toLocaleString("en-NG"), max: Number(op.max_amount).toLocaleString("en-NG") })}
                keyboardType="number-pad"
                prefix="₦"
                value={amount}
                error={errors.amount}
                onChangeText={(v) => setAmount(v.replace(/[^\d,]/g, ""))}
              />
            </View>
          )}
          {estimate ? <Text className="text-ink-600">{t("bills.intl.estimate", { amount: estimate, currency: op.local_currency })}</Text> : null}
        </Card>
      ) : null}
    </Screen>
  );
}
