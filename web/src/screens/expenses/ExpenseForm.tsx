import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router";

import { Banner, Button, Card, LoadingBlock, MoneyInput, PageHeader, Select, TextField, optionsFrom, useToast } from "../../components";
import { strings } from "../../i18n";
import { api } from "../../lib/api";
import { todayISO } from "../../lib/dates";
import { useForm } from "../../lib/form";
import { useIdempotencyKey } from "../../lib/idempotency";
import { formatPlainAmount, isPositive, parseMoneyInput } from "../../lib/money";
import { useOrg } from "../../lib/org";
import { useInvalidateOrg, useOrgQuery } from "../../lib/queries";
import type { Expense, Property } from "../../lib/types";

const t = strings.expenses;

export function ExpenseForm() {
  const { expenseId } = useParams();
  const editing = Boolean(expenseId);
  const { org, base } = useOrg();
  const navigate = useNavigate();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const idem = useIdempotencyKey();
  const properties = useOrgQuery<Property[]>("/properties/");
  const existing = useOrgQuery<Expense>(`/expenses/${expenseId}/`, undefined, { enabled: editing });
  const [busy, setBusy] = useState(false);
  const form = useForm({ property: "", category: "repairs", amount: "", spent_on: todayISO(), vendor: "", description: "" });
  const { setValues } = form;

  useEffect(() => {
    const x = existing.data;
    if (x)
      setValues({
        property: x.property ?? "",
        category: x.category,
        amount: formatPlainAmount(x.amount),
        spent_on: x.spent_on,
        vendor: x.vendor,
        description: x.description,
      });
  }, [existing.data, setValues]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const v = form.values;
    const amount = parseMoneyInput(v.amount);
    if (
      !form.validate({
        amount: amount === null ? strings.fields.amountInvalid : !isPositive(amount) ? strings.fields.amountZero : undefined,
        spent_on: !v.spent_on ? strings.common.required : v.spent_on > todayISO() ? t.futureDate : undefined,
      })
    )
      return;
    const body = {
      property: v.property || null,
      category: v.category,
      amount,
      spent_on: v.spent_on,
      vendor: v.vendor.trim(),
      description: v.description.trim(),
    };
    setBusy(true);
    try {
      await api<Expense>(`/orgs/${org.id}/expenses/${editing ? `${expenseId}/` : ""}`, {
        method: editing ? "PATCH" : "POST",
        body,
        // Only creating is idempotent on the server; editing is naturally safe to repeat.
        idempotencyKey: editing ? undefined : idem.keyFor(body),
      });
      idem.reset();
      await invalidate();
      toast.show(strings.common.saved);
      navigate(`${base}/expenses`);
    } catch (err) {
      form.fromApiError(err);
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader title={editing ? t.edit : t.add} back={{ to: `${base}/expenses`, label: t.title }} />
      {editing && existing.isLoading ? (
        <LoadingBlock />
      ) : editing && existing.error ? (
        <Banner tone="error" onRetry={() => void existing.refetch()}>{strings.errors.loadFailed}</Banner>
      ) : (
        <Card className="max-w-2xl">
          <form onSubmit={submit} noValidate className="space-y-4">
            {form.formError && <Banner tone="error">{form.formError}</Banner>}
            <Select
              label={t.property}
              options={[{ value: "", label: t.general }, ...(properties.data ?? []).map((p) => ({ value: p.id, label: p.name }))]}
              {...form.text("property")}
            />
            <Select label={t.category} options={optionsFrom(t.categories)} {...form.text("category")} />
            <MoneyInput label={strings.fields.amount} value={form.values.amount} onChange={(x) => form.set("amount", x)} error={form.errors.amount} />
            <TextField label={t.spentOn} type="date" max={todayISO()} {...form.text("spent_on")} />
            <TextField label={t.vendor} optional maxLength={120} {...form.text("vendor")} />
            <TextField label={strings.fields.description} optional maxLength={255} {...form.text("description")} />
            <Button type="submit" loading={busy}>
              {strings.common.save}
            </Button>
          </form>
        </Card>
      )}
    </>
  );
}
