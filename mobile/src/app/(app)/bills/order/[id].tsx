import { Ionicons } from "@expo/vector-icons";
import { router, useLocalSearchParams } from "expo-router";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ActivityIndicator, View } from "react-native";

import type { BillOrder } from "@/api";
import { Banner, Button, Card, Screen, Text } from "@/components";
import { BillStatusBadge, SummaryRow } from "@/components/bills";
import { openCheckout } from "@/hooks/useBillCheckout";
import { useBillOrderStatus } from "@/hooks/useBillOrderStatus";
import { formatToken } from "@/lib/bills";
import { copyText } from "@/lib/clipboard";
import { formatDateTime } from "@/lib/date";
import { formatMoney, toKobo } from "@/lib/money";
import { formatPhone } from "@/lib/phone";
import { downloadBillReceipt } from "@/lib/receipts";
import { useSession } from "@/store/session";
import tokens from "@/theme/tokens";

/**
 * After checkout, and from History: poll the order and say plainly where it is. Delivered electricity
 * shows the token large, with a copy button.
 */
export default function BillOrderScreen() {
  const { t } = useTranslation();
  const { id = "" } = useLocalSearchParams<{ id: string }>();
  const { order, checking, failed, linkExpired, checkAgain } = useBillOrderStatus(id);
  const resumeLock = useSession((s) => s.resumeLock);
  const status = order?.status;

  // Back from checkout with an answer: the app lock works normally again.
  useEffect(() => {
    if (status && status !== "awaiting_payment") resumeLock();
  }, [status, resumeLock]);
  useEffect(() => () => resumeLock(), [resumeLock]);

  let icon: keyof typeof Ionicons.glyphMap = "time-outline";
  let color: string = tokens.color.warning[700];
  let title = t("bills.order.checkingTitle");
  let body = t("bills.order.checkingBody");
  if (order) {
    const total = formatMoney(order.total, order.currency);
    switch (order.status) {
      case "awaiting_payment":
        title = t("bills.order.awaitingTitle");
        body = t("bills.order.awaitingBody");
        color = tokens.color.primary[600];
        break;
      case "processing":
        title = t("bills.order.processingTitle");
        body = t("bills.order.processingBody");
        break;
      case "delivered":
        icon = "checkmark-circle";
        color = tokens.color.success[500];
        title = t("bills.order.deliveredTitle");
        body = t("bills.order.deliveredBody", { what: whatOf(order), customer: customerOf(order) });
        break;
      case "refund_pending":
        icon = "return-down-back-outline";
        title = t("bills.order.refundPendingTitle");
        body = t("bills.order.refundPendingBody", { amount: total });
        break;
      case "refunded":
        icon = "return-down-back-outline";
        color = tokens.color.primary[600];
        title = t("bills.order.refundedTitle");
        body = t("bills.order.refundedBody", { amount: total });
        break;
      case "expired":
        icon = "close-circle-outline";
        color = tokens.color.ink[600];
        title = t("bills.order.expiredTitle");
        body = t("bills.order.expiredBody");
        break;
    }
  }

  const showSpinner = !order || (checking && (status === "awaiting_payment" || status === "processing"));
  const canCheckAgain = !checking && status !== "delivered" && status !== "refunded" && status !== "expired";

  return (
    <Screen
      back
      footer={
        <View className="gap-3">
          {status === "awaiting_payment" && order?.checkout_url && !linkExpired ? (
            <Button title={t("bills.order.reopen", { amount: formatMoney(order.total) })} onPress={() => openCheckout(order.checkout_url).then(checkAgain)} />
          ) : null}
          {canCheckAgain ? (
            <Button title={t("bills.order.checkAgain")} variant={status === "awaiting_payment" ? "secondary" : "primary"} onPress={checkAgain} />
          ) : null}
          {status === "delivered" || status === "expired" || status === "refunded" ? (
            <Button
              title={t("bills.order.buyAgain")}
              variant={status === "expired" ? "primary" : "secondary"}
              onPress={() => router.replace({ pathname: "/bills/[category]", params: { category: order!.category } })}
            />
          ) : null}
          <Button title={t("bills.order.backHome")} variant="ghost" onPress={() => router.replace("/")} />
        </View>
      }
    >
      <View className="items-center gap-4 pt-4" accessibilityLiveRegion="polite">
        {showSpinner ? (
          <ActivityIndicator size="large" color={tokens.color.primary[600]} accessibilityLabel={title} />
        ) : (
          <Ionicons name={icon} size={72} color={color} accessibilityElementsHidden />
        )}
        <Text variant="title" className="text-center" accessibilityRole="header">
          {title}
        </Text>
        <Text className="text-center text-ink-600">{body}</Text>
      </View>

      {failed && !checking ? <Banner message={t("bills.order.checkFailed")} onRetry={checkAgain} retryLabel={t("common.retry")} /> : null}

      {order?.status === "delivered" && order.token ? <TokenCard order={order} /> : null}
      {order?.status === "delivered" && order.receipt_number ? <ReceiptButton order={order} /> : null}
      {order ? <OrderSummary order={order} /> : null}
    </Screen>
  );
}

function whatOf(o: BillOrder): string {
  return [o.biller_name, o.plan_name && o.category !== "electricity" ? o.plan_name : null].filter(Boolean).join(" · ");
}

function customerOf(o: BillOrder): string {
  const id = o.category === "airtime" || o.category === "data" ? formatPhone(localToE164(o.customer_id)) : o.customer_id;
  return o.customer_name ? `${id} (${o.customer_name})` : id;
}

/** Orders store phone numbers in the local 080… form. */
function localToE164(id: string): string {
  return /^0\d{10}$/.test(id) ? `+234${id.slice(1)}` : id;
}

function TokenCard({ order }: { order: BillOrder }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState<"copied" | "failed" | null>(null);
  const pretty = formatToken(order.token);

  const copy = async () => {
    const result = await copyText(order.token);
    setCopied(result === "failed" ? "failed" : "copied");
  };

  return (
    <Card tone="navy" testID="token-card">
      <Text variant="label" className="text-sky-100">
        {t("bills.order.tokenLabel")}
      </Text>
      <Text
        variant="display"
        selectable
        className="text-white"
        accessibilityLabel={t("bills.order.tokenA11y", { token: order.token.split("").join(" ") })}
      >
        {pretty}
      </Text>
      {order.units ? (
        <Text variant="label" className="text-white">
          {t("bills.order.units", { units: order.units })}
        </Text>
      ) : null}
      <Text className="text-sky-100">{t("bills.order.tokenHint")}</Text>
      <Button
        title={copied === "copied" ? t("bills.order.copied") : t("bills.order.copyToken")}
        variant="secondary"
        onPress={copy}
      />
      {copied === "failed" ? <Banner message={t("bills.order.copyFailed")} /> : null}
    </Card>
  );
}

function ReceiptButton({ order }: { order: BillOrder }) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const get = async () => {
    setBusy(true);
    setError(null);
    try {
      await downloadBillReceipt(order.id, order.receipt_number);
    } catch {
      setError(t("bills.order.receiptFailed"));
    } finally {
      setBusy(false);
    }
  };
  return (
    <View className="gap-3">
      {error ? <Banner message={error} onRetry={get} retryLabel={t("common.retry")} /> : null}
      <Button title={t("bills.order.downloadReceipt")} variant="secondary" loading={busy} loadingLabel={t("bills.order.downloading")} onPress={get} />
    </View>
  );
}

function OrderSummary({ order: o }: { order: BillOrder }) {
  const { t } = useTranslation();
  return (
    <Card>
      <View className="flex-row flex-wrap items-center justify-between gap-2">
        <Text variant="label">{t("bills.order.summary")}</Text>
        <BillStatusBadge status={o.status} />
      </View>
      <SummaryRow label={t("bills.review.what")} value={[o.biller_name, o.plan_name].filter(Boolean).join(" · ")} />
      <SummaryRow label={t(`bills.customerLabel.${o.category}`)} value={customerOf(o)} />
      <SummaryRow label={t("bills.review.amount")} value={formatMoney(o.amount, o.currency)} />
      <SummaryRow
        label={t("bills.review.fee")}
        value={toKobo(o.fee_waived ?? "0") > 0 ? t("bills.review.feeFree") : formatMoney(o.fee, o.currency)}
      />
      <SummaryRow label={t("bills.review.total")} value={formatMoney(o.total, o.currency)} strong />
      {o.receipt_number ? <SummaryRow label={t("bills.order.receipt")} value={o.receipt_number} /> : null}
      <SummaryRow label={t("bills.order.reference")} value={o.reference} />
      <SummaryRow label={t("bills.order.date")} value={formatDateTime(o.created_at)} />
    </Card>
  );
}
