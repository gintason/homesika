import { useState, type FormEvent } from "react";
import { useSearchParams } from "react-router";

import { Banner, Button, ButtonLink, Card, MoneyInput, PageHeader, Select, TextField, useToast } from "../../components";
import { fmt, strings } from "../../i18n";
import { api } from "../../lib/api";
import { formatDate } from "../../lib/dates";
import { useForm } from "../../lib/form";
import { useIdempotencyKey } from "../../lib/idempotency";
import { compareMoney, formatMoney, isPositive, parseMoneyInput, sumMoney } from "../../lib/money";
import { useOrg } from "../../lib/org";
import { useInvalidateOrg, useOrgQuery } from "../../lib/queries";
import type { PaymentLink, Tenant } from "../../lib/types";
import { ChargePicker } from "../ChargePicker";
import { LinkShare } from "./LinkShare";

const t = strings.links;

export function CreatePaymentLink() {
  const { org, base } = useOrg();
  const [params] = useSearchParams();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const idem = useIdempotencyKey();
  const tenants = useOrgQuery<Tenant[]>("/tenants/");
  const [busy, setBusy] = useState(false);
  const [total, setTotal] = useState("0.00");
  const [created, setCreated] = useState<PaymentLink | null>(null);
  const form = useForm({ tenant: params.get("tenant") ?? "", charges: [] as string[], amount: "", description: "" });
  const v = form.values;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const amount = v.amount ? parseMoneyInput(v.amount) : null;
    if (
      !form.validate({
        tenant: v.tenant ? undefined : strings.common.required,
        charges: v.charges.length ? undefined : t.pickChargesRequired,
        amount: !v.amount
          ? undefined
          : amount === null
            ? strings.fields.amountInvalid
            : !isPositive(amount) || compareMoney(amount, total) > 0
              ? fmt(t.partAmountHint, { total: formatMoney(total, org.currency) })
              : undefined,
      })
    )
      return;
    const body: Record<string, unknown> = { tenant: v.tenant, charges: v.charges, description: v.description.trim() };
    if (amount) body.amount = amount;
    setBusy(true);
    try {
      const link = await api<PaymentLink>(`/orgs/${org.id}/payment-links/`, {
        method: "POST",
        body,
        idempotencyKey: idem.keyFor(body),
      });
      idem.reset();
      await invalidate();
      toast.show(t.created);
      setCreated(link);
    } catch (err) {
      form.fromApiError(err);
    } finally {
      setBusy(false);
    }
  };

  if (created) {
    return (
      <>
        <PageHeader title={t.created} back={{ to: `${base}/payment-links`, label: t.title }} />
        <Card className="max-w-2xl space-y-4">
          <p className="text-base text-ink-700">
            {t.createdIntro} <strong>{created.tenant_name}</strong> · {formatMoney(created.amount, created.currency)} ·{" "}
            {t.expires.toLowerCase()} {formatDate(created.expires_at)}
          </p>
          <LinkShare url={created.url} />
          <div className="flex flex-wrap gap-2 pt-2">
            <ButtonLink to={`${base}/payment-links`} variant="ghost">
              {t.title}
            </ButtonLink>
          </div>
        </Card>
      </>
    );
  }

  return (
    <>
      <PageHeader title={t.create} description={t.createIntro} back={{ to: `${base}/payment-links`, label: t.title }} />
      <Card className="max-w-2xl">
        <form onSubmit={submit} noValidate className="space-y-4">
          {form.formError && <Banner tone="error">{form.formError}</Banner>}
          <Select
            label={strings.payments.tenant}
            placeholder={strings.leases.pickTenant}
            options={(tenants.data ?? []).map((x) => ({ value: x.id, label: x.full_name }))}
            disabled={tenants.isLoading}
            {...form.text("tenant")}
            onChange={(e) => {
              form.set("tenant", e.target.value);
              form.set("charges", []);
              setTotal("0.00");
            }}
          />
          <ChargePicker
            tenantId={v.tenant}
            legend={t.pickCharges}
            selected={v.charges}
            error={form.errors.charges}
            onChange={(ids, charges) => {
              form.set("charges", ids);
              setTotal(sumMoney(charges.map((c) => c.balance)));
            }}
          />
          {v.charges.length > 0 && (
            <p className="text-base">
              {t.total}: <strong>{formatMoney(total, org.currency)}</strong>
            </p>
          )}
          <MoneyInput
            label={t.partAmount}
            optional
            hint={fmt(t.partAmountHint, { total: formatMoney(total, org.currency) })}
            value={v.amount}
            onChange={(x) => form.set("amount", x)}
            error={form.errors.amount}
          />
          <TextField label={strings.fields.description} optional maxLength={200} {...form.text("description")} />
          <Button type="submit" loading={busy}>
            {t.create}
          </Button>
        </form>
      </Card>
    </>
  );
}
