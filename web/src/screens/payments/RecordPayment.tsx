import { useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router";

import { Banner, Button, Card, MoneyInput, PageHeader, Select, TextField, optionsFrom, useToast } from "../../components";
import { strings } from "../../i18n";
import { api } from "../../lib/api";
import { localInputToISO, nowLocalInput } from "../../lib/dates";
import { useForm } from "../../lib/form";
import { useIdempotencyKey } from "../../lib/idempotency";
import { formatPlainAmount, isPositive, parseMoneyInput, sumMoney } from "../../lib/money";
import { useOrg } from "../../lib/org";
import { useInvalidateOrg, useOrgQuery } from "../../lib/queries";
import type { Payment, Tenant } from "../../lib/types";
import { ChargePicker } from "../ChargePicker";

const t = strings.payments;
const CHANNELS = { cash: t.channels.cash, bank_transfer: t.channels.bank_transfer, pos: t.channels.pos, cheque: t.channels.cheque };

/** Record cash / transfer / POS / cheque received directly. POST /payments/manual/ with an Idempotency-Key. */
export function RecordPayment() {
  const { org, base } = useOrg();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const idem = useIdempotencyKey();
  const tenants = useOrgQuery<Tenant[]>("/tenants/");
  const [busy, setBusy] = useState(false);
  const [autoAmount, setAutoAmount] = useState(true);
  const form = useForm({
    tenant: params.get("tenant") ?? "",
    amount: "",
    channel: "bank_transfer",
    paid_at: nowLocalInput(),
    note: "",
    charges: [] as string[],
  });
  const v = form.values;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const amount = parseMoneyInput(v.amount);
    const paidAt = localInputToISO(v.paid_at);
    if (
      !form.validate({
        tenant: v.tenant ? undefined : strings.common.required,
        amount: amount === null ? strings.fields.amountInvalid : !isPositive(amount) ? strings.fields.amountZero : undefined,
        channel: v.channel ? undefined : strings.common.required,
        paid_at: !paidAt ? strings.common.required : new Date(paidAt).getTime() > Date.now() + 60_000 ? t.paidAtFuture : undefined,
      })
    )
      return;
    const body = { tenant: v.tenant, amount, channel: v.channel, paid_at: paidAt, note: v.note.trim(), charges: v.charges };
    setBusy(true);
    try {
      const payment = await api<Payment>(`/orgs/${org.id}/payments/manual/`, {
        method: "POST",
        body,
        idempotencyKey: idem.keyFor(body),
      });
      idem.reset();
      await invalidate();
      toast.show(t.recorded);
      navigate(`${base}/payments/${payment.id}`);
    } catch (err) {
      form.fromApiError(err);
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader title={t.recordTitle} description={t.recordIntro} back={{ to: `${base}/payments`, label: t.title }} />
      <Card className="max-w-2xl">
        <form onSubmit={submit} noValidate className="space-y-4">
          {form.formError && <Banner tone="error">{form.formError}</Banner>}
          <Select
            label={t.tenant}
            placeholder={strings.leases.pickTenant}
            options={(tenants.data ?? []).map((x) => ({ value: x.id, label: x.full_name }))}
            disabled={tenants.isLoading}
            {...form.text("tenant")}
            onChange={(e) => {
              form.set("tenant", e.target.value);
              form.set("charges", []);
            }}
          />
          <ChargePicker
            tenantId={v.tenant}
            legend={t.applyTo}
            hint={t.applyToHint}
            selected={v.charges}
            onChange={(ids, charges) => {
              form.set("charges", ids);
              if (autoAmount) form.set("amount", charges.length ? formatPlainAmount(sumMoney(charges.map((c) => c.balance))) : "");
            }}
          />
          <MoneyInput
            label={strings.fields.amount}
            value={v.amount}
            onChange={(x) => {
              setAutoAmount(false);
              form.set("amount", x);
            }}
            error={form.errors.amount}
          />
          <Select label={t.channel} options={optionsFrom(CHANNELS)} {...form.text("channel")} />
          <TextField label={t.paidAt} type="datetime-local" max={nowLocalInput()} {...form.text("paid_at")} />
          <TextField label={t.note} optional maxLength={255} {...form.text("note")} />
          <Button type="submit" loading={busy}>
            {t.record}
          </Button>
        </form>
      </Card>
    </>
  );
}
