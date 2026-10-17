import { router, useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { View } from "react-native";

import { billsApi, type BillCategory, type BillCustomer, type Biller, type BillOrderInput, type BillPlan } from "@/api";
import { Banner, Button, Card, EmptyState, PhoneInput, Screen, SkeletonCard, Text, TextField } from "@/components";
import { ChoiceChips, PlanList, SummaryRow } from "@/components/bills";
import { useBillsCatalogue, useLeases, useReferral } from "@/hooks/queries";
import { billErrorText, useBillCheckout } from "@/hooks/useBillCheckout";
import { errorText } from "@/lib/api";
import {
  detailText,
  digitsOnly,
  isBillCategory,
  leaseWithMeter,
  matchDisco,
  parseNairaAmount,
  quickAmounts,
  type AmountError,
} from "@/lib/bills";
import { formatKobo, formatMoney, fromKobo, toKobo } from "@/lib/money";
import { formatPhone, normalisePhone } from "@/lib/phone";
import { useSession } from "@/store/session";

/** /bills/[category]: the form for one category, then a review step, then checkout. */
export default function BillFormScreen() {
  const { t } = useTranslation();
  const { category } = useLocalSearchParams<{ category: string }>();
  if (!isBillCategory(category)) {
    return (
      <Screen back>
        <EmptyState icon="alert-circle-outline" title={t("bills.notFound")} action={<Button title={t("bills.title")} onPress={() => router.replace("/bills")} />} />
      </Screen>
    );
  }
  return <BillForm key={category} category={category} />;
}

const PHONE_CATEGORIES: BillCategory[] = ["airtime", "data"];

/** Prepaid/postpaid get our own (translated) names; other plans keep the provider's name. */
/** Helpers get `t` with a plain signature: the typed key union is too large to check through a parameter. */
type PlainT = (key: string, options?: Record<string, unknown>) => string;

function planLabel(t: PlainT, plan: BillPlan): string {
  if (plan.code === "prepaid" || plan.code === "postpaid") return t(`bills.meterTypes.${plan.code}`);
  return plan.name;
}

/** "08012345678" for display/input from my +234 number. */
function localPhone(e164: string | undefined): string {
  if (!e164) return "";
  return e164.startsWith("+234") ? e164.slice(4) : e164;
}

function BillForm({ category }: { category: BillCategory }) {
  const { t } = useTranslation();
  const myPhone = useSession((s) => s.profile?.phone);
  const catalogue = useBillsCatalogue(category);
  const isPower = category === "electricity";
  const leases = useLeases({ enabled: isPower });
  const checkout = useBillCheckout();
  const referral = useReferral();

  const [billerId, setBillerId] = useState<string | null>(null);
  const [planId, setPlanId] = useState<string | null>(null);
  const [customerInput, setCustomerInput] = useState<string | null>(null);
  const [amountRaw, setAmountRaw] = useState("");
  const [showErrors, setShowErrors] = useState(false);
  const [verified, setVerified] = useState<{ key: string; customer: BillCustomer } | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [verifyError, setVerifyError] = useState<{ key: string; message: string } | null>(null);
  const [step, setStep] = useState<"form" | "review">("form");

  const billers = catalogue.data ?? [];
  const homeLease = isPower ? leaseWithMeter(leases.data) : null;
  const homeDisco = isPower ? matchDisco(billers, homeLease?.disco) : null;

  // Defaults are derived (not copied into state), so they follow the data as it loads.
  const biller: Biller | null =
    billers.find((b) => b.id === billerId) ?? homeDisco ?? (billers.length === 1 ? (billers[0] ?? null) : null);
  const plans = biller?.plans ?? [];
  const plan: BillPlan | null =
    plans.find((p) => p.id === planId) ?? (isPower ? (plans.find((p) => p.code === "prepaid") ?? plans[0] ?? null) : null);
  const customer = customerInput ?? (PHONE_CATEGORIES.includes(category) ? localPhone(myPhone) : (homeLease?.meter_number ?? ""));
  const usingHomeMeter = Boolean(isPower && homeLease && digitsOnly(customer) && digitsOnly(customer) === digitsOnly(homeLease.meter_number ?? ""));

  // ---- validation --------------------------------------------------------------------------------
  const needsPlan = category !== "airtime";
  const fixedPrice = plan?.price ?? null;
  const amountResult = fixedPrice ? ({ amount: fixedPrice } as const) : parseNairaAmount(amountRaw, biller);
  const amount = "amount" in amountResult ? amountResult.amount : null;

  const customerId = PHONE_CATEGORIES.includes(category) ? normalisePhone(customer) : digitsOnly(customer);
  const customerValid = PHONE_CATEGORIES.includes(category)
    ? /^\+234\d{10}$/.test(customerId)
    : customerId.length >= 6 && customerId.length <= 20;

  // TV: the owner doesn't depend on the bouquet. Electricity: it depends on prepaid/postpaid.
  const verifyKey = `${biller?.id ?? ""}|${isPower ? (plan?.id ?? "") : ""}|${customerId}`;
  const needsVerify = Boolean(biller?.requires_verification);
  const verifiedCustomer = verified?.key === verifyKey ? verified.customer : null;
  const currentVerifyError = verifyError?.key === verifyKey ? verifyError.message : null;

  const amountMessage = (e: AmountError) =>
    t(`bills.amountErrors.${e}`, {
      min: formatMoney(biller?.min_amount ?? "0"),
      max: formatMoney(biller?.max_amount ?? "0"),
    });
  const amountError =
    "error" in amountResult && (showErrors || (amountRaw.trim() !== "" && amountResult.error !== "required"))
      ? amountMessage(amountResult.error)
      : undefined;
  const billerError = showErrors && !biller ? t(`bills.billerRequired.${category}`) : undefined;
  const planError = showErrors && needsPlan && !plan ? t("bills.planRequired") : undefined;
  const customerError =
    currentVerifyError ??
    (showErrors && !customerValid ? t(PHONE_CATEGORIES.includes(category) ? "bills.phoneInvalid" : "bills.customerInvalid") : undefined);

  const formValid = Boolean(biller && (!needsPlan || plan) && amount && customerValid);

  // ---- actions -----------------------------------------------------------------------------------
  const verify = async (): Promise<boolean> => {
    if (!biller || verifying) return false;
    if (!customerValid || (isPower && !plan)) {
      setShowErrors(true);
      return false;
    }
    const key = verifyKey;
    setVerifying(true);
    setVerifyError(null);
    try {
      const result = await billsApi.verify({
        biller: biller.id,
        customer_id: customerId,
        ...(isPower && plan ? { plan: plan.id } : {}),
      });
      setVerified({ key, customer: result });
      return true;
    } catch (e) {
      setVerifyError({ key, message: billErrorText(e) });
      return false;
    } finally {
      setVerifying(false);
    }
  };

  const toReview = async () => {
    setShowErrors(true);
    if (!formValid) return;
    if (needsVerify && !verifiedCustomer && !(await verify())) return;
    checkout.reset();
    setStep("review");
  };

  const orderInput = (): BillOrderInput | null => {
    if (!biller || !amount) return null;
    const input: BillOrderInput = {
      biller: biller.id,
      // The server's normalised number from verify, else what we validated.
      customer_id: verifiedCustomer?.customer_id || customerId,
    };
    if (plan) input.plan = plan.id;
    if (!fixedPrice) input.amount = amount;
    if (usingHomeMeter && homeLease?.unit) input.unit = homeLease.unit;
    return input;
  };

  const editAgain = () => {
    checkout.reset();
    setStep("form");
  };

  // ---- render ------------------------------------------------------------------------------------
  const title = t(`bills.category.${category}`);

  if (catalogue.isPending && !catalogue.error) {
    return (
      <Screen title={title} back>
        <SkeletonCard label={t("common.loading")} lines={5} />
      </Screen>
    );
  }
  if (!catalogue.data) {
    return (
      <Screen title={title} back>
        <Banner message={`${t("errors.loadFailed")} ${errorText(catalogue.error)}`} onRetry={() => catalogue.refetch()} retryLabel={t("common.retry")} />
      </Screen>
    );
  }
  if (billers.length === 0) {
    return (
      <Screen title={title} back>
        <EmptyState icon="time-outline" title={t("bills.noBillers")} body={t("bills.noBillersBody")} />
      </Screen>
    );
  }

  if (step === "review" && biller && amount) {
    const input = orderInput();
    const created = checkout.order;
    const what = [biller.name, plan ? planLabel(t as unknown as PlainT, plan) : null].filter(Boolean).join(" · ");
    const forWhom = PHONE_CATEGORIES.includes(category) ? formatPhone(customerId) : customerId;
    const address = detailText(verifiedCustomer?.details, "customer_address");
    // The fee from the catalogue is shown up front; if the server's total still differs, the
    // created order's figures replace these and the person is asked again.
    const catalogueFee = biller.fee ?? "0.00";
    // An invite reward makes the next service fee free (the server applies it; this only shows it).
    const freeFee = !created && toKobo(catalogueFee) > 0 && (referral.data?.waivers_available ?? 0) > 0;
    const fee = created ? created.fee : freeFee ? "0.00" : catalogueFee;
    const total = created ? created.total : fromKobo(toKobo(amount) + toKobo(fee));
    const payAmount = total;
    return (
      <Screen
        title={t("bills.review.title")}
        back
        footer={
          <View className="gap-3">
            <Button
              title={t("bills.pay", { amount: formatMoney(payAmount) })}
              loading={checkout.busy}
              loadingLabel={t("bills.starting")}
              onPress={() => input && checkout.submit(input, total)}
            />
            <Button title={t("bills.review.edit")} variant="ghost" onPress={editAgain} disabled={checkout.busy} />
          </View>
        }
      >
        <Card>
          <SummaryRow label={t("bills.review.what")} value={what} />
          <SummaryRow label={t(`bills.customerLabel.${category}`)} value={forWhom} />
          {verifiedCustomer?.name ? <SummaryRow label={t("bills.review.name")} value={verifiedCustomer.name} /> : null}
          {address ? <SummaryRow label={t("bills.review.address")} value={address} /> : null}
          <View className="h-px bg-surface-line" />
          <SummaryRow label={t("bills.review.amount")} value={formatMoney(created ? created.amount : amount)} />
          {toKobo(fee) > 0 ? <SummaryRow label={t("bills.review.fee")} value={formatMoney(fee)} /> : null}
          {freeFee || (created && toKobo(created.fee_waived) > 0) ? (
            <SummaryRow label={t("bills.review.fee")} value={t("bills.review.feeFree")} />
          ) : null}
          <SummaryRow label={t("bills.review.total")} value={formatMoney(total)} strong />
        </Card>
        {created ? (
          <Banner tone="info" message={t("bills.review.feeAdded", { fee: formatMoney(created.fee), total: formatMoney(created.total) })} />
        ) : null}
        {checkout.error ? <Banner message={checkout.error} /> : null}
        <Text className="text-ink-600">{t("bills.howItWorks")}</Text>
      </Screen>
    );
  }

  const chips = fixedPrice ? [] : quickAmounts(category, biller);
  const minMaxHint =
    biller?.min_amount && biller?.max_amount
      ? t("bills.amountHint", { min: formatMoney(biller.min_amount), max: formatMoney(biller.max_amount) })
      : t("bills.amountHintAny");

  return (
    <Screen
      title={title}
      back
      footer={
        <Button
          title={t("common.continue")}
          loading={verifying}
          loadingLabel={t("bills.verifying")}
          onPress={toReview}
        />
      }
    >
      {isPower && homeLease && !homeDisco && homeLease.disco ? <Banner tone="info" message={t("bills.discoUnknown")} /> : null}
      <Card>
        <ChoiceChips
          label={t(`bills.billerLabel.${category}`)}
          choices={billers.map((b) => ({ value: b.id, label: b.name }))}
          value={biller?.id ?? null}
          onChange={(id) => {
            setBillerId(id);
            setPlanId(null);
          }}
        />
        {billerError ? (
          <Text variant="caption" className="text-danger-700" accessibilityRole="alert">
            {billerError}
          </Text>
        ) : null}

        {isPower && biller && plans.length > 0 ? (
          <ChoiceChips
            label={t("bills.meterType")}
            choices={plans.map((p) => ({ value: p.id, label: planLabel(t as unknown as PlainT, p) }))}
            value={plan?.id ?? null}
            onChange={setPlanId}
          />
        ) : null}

        {PHONE_CATEGORIES.includes(category) ? (
          <PhoneInput
            label={t("bills.customerLabel.phone")}
            hint={t("bills.phoneHint")}
            error={customerError}
            value={customer}
            onChangeText={setCustomerInput}
          />
        ) : (
          <View className="gap-3">
            <TextField
              label={t(`bills.customerLabel.${category}`)}
              hint={usingHomeMeter && homeLease ? t("bills.meterFromHome", { unit: `${homeLease.property_name} · ${homeLease.unit_label}` }) : undefined}
              error={customerError ?? undefined}
              value={customer}
              onChangeText={(v) => setCustomerInput(v.replace(/[^\d\s-]/g, "").slice(0, 24))}
              keyboardType="number-pad"
            />
            {needsVerify ? (
              verifiedCustomer ? (
                <Banner tone="success" message={verifiedText(t as unknown as PlainT, verifiedCustomer)} />
              ) : (
                <Button
                  title={t(`bills.verify.${category === "cable_tv" ? "cable_tv" : "electricity"}`)}
                  variant="secondary"
                  loading={verifying}
                  loadingLabel={t("bills.verifying")}
                  onPress={verify}
                />
              )
            ) : null}
          </View>
        )}
      </Card>

      {needsPlan && !isPower && biller ? (
        <Card>
          {plans.length > 0 ? (
            <PlanList
              label={t(category === "cable_tv" ? "bills.bouquet" : "bills.plan")}
              plans={plans}
              value={plan?.id ?? null}
              onChange={setPlanId}
            />
          ) : (
            <Text className="text-ink-600">{t("bills.noPlans")}</Text>
          )}
          {planError ? (
            <Text variant="caption" className="text-danger-700" accessibilityRole="alert">
              {planError}
            </Text>
          ) : null}
        </Card>
      ) : null}

      {!fixedPrice && (category === "airtime" || isPower || plan) ? (
        <Card>
          <TextField
            label={t("bills.amount")}
            hint={minMaxHint}
            error={amountError}
            value={amountRaw}
            onChangeText={setAmountRaw}
            keyboardType="number-pad"
            prefix="₦"
          />
          {chips.length > 0 ? (
            <ChoiceChips
              label={t("bills.quickAmounts")}
              hideLabel
              choices={chips.map((n) => ({ value: String(n), label: formatKobo(n * 100).replace(/\.00$/, "") }))}
              value={amount ? String(Number(amount.split(".")[0])) : null}
              onChange={setAmountRaw}
            />
          ) : null}
        </Card>
      ) : null}

      <Text className="text-ink-600">{t("bills.howItWorks")}</Text>
    </Screen>
  );
}

function verifiedText(t: PlainT, c: BillCustomer): string {
  const address = detailText(c.details, "customer_address");
  const bouquet = detailText(c.details, "current_bouquet");
  return [
    t("bills.verifiedAs", { name: c.name }),
    address ? t("bills.verifiedAddress", { address }) : null,
    bouquet ? t("bills.currentBouquet", { bouquet }) : null,
  ]
    .filter(Boolean)
    .join("\n");
}
