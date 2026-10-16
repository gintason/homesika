import { useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router";

import { Banner, Button, Card, MoneyInput, PageHeader, Select, TextArea, TextField, optionsFrom, useToast } from "../../components";
import { strings } from "../../i18n";
import { api } from "../../lib/api";
import { addYearsMinusDay } from "../../lib/dates";
import { useForm } from "../../lib/form";
import { formatPlainAmount, isPositive, parseMoneyInput } from "../../lib/money";
import { useOrg } from "../../lib/org";
import { useInvalidateOrg, useOrgQuery } from "../../lib/queries";
import type { Lease, Tenant, Unit } from "../../lib/types";

const t = strings.leases;

/** Creates a DRAFT lease; it is activated from the lease page (which generates the charges). */
export function LeaseForm() {
  const { org, base } = useOrg();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const units = useOrgQuery<Unit[]>("/units/");
  const tenants = useOrgQuery<Tenant[]>("/tenants/");
  const [busy, setBusy] = useState(false);
  const form = useForm({
    unit: params.get("unit") ?? "",
    tenant: params.get("tenant") ?? "",
    start_date: "",
    end_date: "",
    rent_amount: "",
    rent_frequency: "annual",
    service_charge_amount: "",
    deposit_amount: "",
    notes: "",
  });
  const v = form.values;

  const onUnit = (id: string) => {
    form.set("unit", id);
    const unit = units.data?.find((u) => u.id === id);
    if (unit?.default_rent_amount && !v.rent_amount) form.set("rent_amount", formatPlainAmount(unit.default_rent_amount));
  };

  const onStart = (value: string) => {
    form.set("start_date", value);
    if (value && !v.end_date) form.set("end_date", addYearsMinusDay(value, 1));
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const rent = parseMoneyInput(v.rent_amount);
    const service = v.service_charge_amount ? parseMoneyInput(v.service_charge_amount) : "0.00";
    const deposit = v.deposit_amount ? parseMoneyInput(v.deposit_amount) : "0.00";
    const req = strings.common.required;
    if (
      !form.validate({
        unit: v.unit ? undefined : req,
        tenant: v.tenant ? undefined : req,
        start_date: v.start_date ? undefined : req,
        end_date: !v.end_date ? req : v.start_date && v.end_date <= v.start_date ? t.endBeforeStart : undefined,
        rent_amount: rent === null ? strings.fields.amountInvalid : !isPositive(rent) ? strings.fields.amountZero : undefined,
        service_charge_amount: service === null ? strings.fields.amountInvalid : undefined,
        deposit_amount: deposit === null ? strings.fields.amountInvalid : undefined,
      })
    )
      return;
    setBusy(true);
    try {
      const lease = await api<Lease>(`/orgs/${org.id}/leases/`, {
        method: "POST",
        body: {
          unit: v.unit,
          tenant: v.tenant,
          start_date: v.start_date,
          end_date: v.end_date,
          rent_amount: rent,
          rent_frequency: v.rent_frequency,
          service_charge_amount: service,
          deposit_amount: deposit,
          notes: v.notes,
          activate: false,
        },
      });
      await invalidate();
      toast.show(t.created);
      navigate(`${base}/leases/${lease.id}`);
    } catch (err) {
      form.fromApiError(err);
      setBusy(false);
    }
  };

  const unitOptions = (units.data ?? []).map((u) => ({
    value: u.id,
    label: `${u.property_name} · ${u.label} (${strings.units.statuses[u.status]})`,
  }));
  const tenantOptions = (tenants.data ?? []).map((x) => ({ value: x.id, label: x.full_name }));

  return (
    <>
      <PageHeader title={t.new} description={t.draftNote} back={{ to: `${base}/leases`, label: t.title }} />
      <Card className="max-w-2xl">
        <form onSubmit={submit} noValidate className="space-y-4">
          {form.formError && <Banner tone="error">{form.formError}</Banner>}
          {(units.error || tenants.error) && (
            <Banner tone="error" onRetry={() => void Promise.all([units.refetch(), tenants.refetch()])}>
              {strings.errors.loadFailed}
            </Banner>
          )}
          <Select
            label={t.unit}
            placeholder={t.pickUnit}
            options={unitOptions}
            hint={units.data && units.data.length === 0 ? t.noUnits : undefined}
            disabled={units.isLoading}
            {...form.text("unit")}
            onChange={(e) => onUnit(e.target.value)}
          />
          <Select
            label={t.tenant}
            placeholder={t.pickTenant}
            options={tenantOptions}
            hint={tenants.data && tenants.data.length === 0 ? t.noTenants : undefined}
            disabled={tenants.isLoading}
            {...form.text("tenant")}
          />
          <div className="grid gap-4 sm:grid-cols-2">
            <TextField label={t.startDate} type="date" {...form.text("start_date")} onChange={(e) => onStart(e.target.value)} />
            <TextField label={t.endDate} type="date" {...form.text("end_date")} />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <MoneyInput label={t.rentAmount} value={v.rent_amount} onChange={(x) => form.set("rent_amount", x)} error={form.errors.rent_amount} />
            <Select label={t.frequency} options={optionsFrom(t.frequencies)} {...form.text("rent_frequency")} />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <MoneyInput
              label={t.serviceCharge}
              optional
              value={v.service_charge_amount}
              onChange={(x) => form.set("service_charge_amount", x)}
              error={form.errors.service_charge_amount}
            />
            <MoneyInput
              label={t.deposit}
              optional
              value={v.deposit_amount}
              onChange={(x) => form.set("deposit_amount", x)}
              error={form.errors.deposit_amount}
            />
          </div>
          <TextArea label={strings.fields.notes} optional {...form.text("notes")} />
          <Button type="submit" loading={busy}>
            {strings.common.create}
          </Button>
        </form>
      </Card>
    </>
  );
}
