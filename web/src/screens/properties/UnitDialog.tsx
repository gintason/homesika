import { useState, type FormEvent } from "react";

import { Banner, Button, Dialog, MoneyInput, Select, TextField, optionsFrom, useToast } from "../../components";
import { strings } from "../../i18n";
import { api } from "../../lib/api";
import { useForm } from "../../lib/form";
import { formatPlainAmount, parseMoneyInput } from "../../lib/money";
import { useOrg } from "../../lib/org";
import { useInvalidateOrg } from "../../lib/queries";
import type { Unit } from "../../lib/types";

const t = strings.units;

/** Create or edit a unit of a property. Mount with a key so it starts fresh each time it opens. */
export function UnitDialog({ propertyId, unit, onClose }: { propertyId: string; unit: Unit | null; onClose: () => void }) {
  const { org } = useOrg();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const [busy, setBusy] = useState(false);
  const form = useForm({
    label: unit?.label ?? "",
    kind: unit?.kind ?? "flat",
    bedrooms: unit?.bedrooms != null ? String(unit.bedrooms) : "",
    default_rent_amount: unit?.default_rent_amount ? formatPlainAmount(unit.default_rent_amount) : "",
    status: unit?.status ?? "vacant",
    meter_number: unit?.meter_number ?? "",
    disco: unit?.disco ?? "",
  });
  const v = form.values;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const rent = v.default_rent_amount ? parseMoneyInput(v.default_rent_amount) : null;
    if (
      !form.validate({
        label: v.label.trim() ? undefined : strings.common.required,
        bedrooms: !v.bedrooms || /^\d{1,2}$/.test(v.bedrooms) ? undefined : strings.common.required,
        default_rent_amount: !v.default_rent_amount || rent !== null ? undefined : strings.fields.amountInvalid,
      })
    )
      return;
    setBusy(true);
    try {
      await api(`/orgs/${org.id}/properties/${propertyId}/units/${unit ? `${unit.id}/` : ""}`, {
        method: unit ? "PATCH" : "POST",
        body: {
          label: v.label.trim(),
          kind: v.kind,
          bedrooms: v.bedrooms ? Number(v.bedrooms) : null,
          default_rent_amount: rent,
          status: v.status,
          meter_number: v.meter_number.trim(),
          disco: v.disco.trim(),
        },
      });
      await invalidate();
      toast.show(strings.common.saved);
      onClose();
    } catch (err) {
      form.fromApiError(err);
      setBusy(false);
    }
  };

  return (
    <Dialog open onClose={onClose} title={unit ? t.edit : t.add}>
      <form onSubmit={submit} noValidate className="space-y-4">
        {form.formError && <Banner tone="error">{form.formError}</Banner>}
        <TextField label={t.label} hint={t.labelHint} required {...form.text("label")} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Select label={t.kind} options={optionsFrom(t.kinds)} {...form.text("kind")} />
          <TextField label={t.bedrooms} optional inputMode="numeric" {...form.text("bedrooms")} />
        </div>
        <MoneyInput
          label={t.defaultRent}
          optional
          value={v.default_rent_amount}
          onChange={(x) => form.set("default_rent_amount", x)}
          error={form.errors.default_rent_amount}
        />
        <Select label={t.status} options={optionsFrom(t.statuses)} {...form.text("status")} />
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField label={t.meter} optional {...form.text("meter_number")} />
          <TextField label={t.disco} optional {...form.text("disco")} />
        </div>
        <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            {strings.common.cancel}
          </Button>
          <Button type="submit" loading={busy}>
            {strings.common.save}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
