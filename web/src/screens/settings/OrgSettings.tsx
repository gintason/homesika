import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { Banner, Button, Card, PhoneInput, Select, Switch, TextArea, TextField, optionsFrom, useToast } from "../../components";
import { strings } from "../../i18n";
import { api } from "../../lib/api";
import { useForm } from "../../lib/form";
import { useOrg } from "../../lib/org";
import { formatPhone, isValidNigerianPhone, normalisePhone } from "../../lib/phone";
import type { Organization } from "../../lib/types";

const t = strings.settings;

export function OrgSettings() {
  const { org, can } = useOrg();
  const qc = useQueryClient();
  const toast = useToast();
  const manage = can("org.manage");
  const [busy, setBusy] = useState(false);
  const form = useForm({
    name: org.name,
    kind: org.kind,
    phone_number: org.phone_number ? formatPhone(org.phone_number) : "",
    email: org.email,
    address: org.address,
    rent_reminders_enabled: org.rent_reminders_enabled,
  });
  const v = form.values;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (
      !form.validate({
        name: v.name.trim() ? undefined : strings.common.required,
        phone_number: !v.phone_number || isValidNigerianPhone(v.phone_number) ? undefined : strings.fields.phoneInvalid,
      })
    )
      return;
    setBusy(true);
    try {
      await api<Organization>(`/orgs/${org.id}/`, {
        method: "PATCH",
        body: {
          name: v.name.trim(),
          kind: v.kind,
          phone_number: v.phone_number ? normalisePhone(v.phone_number) : "",
          email: v.email.trim(),
          address: v.address.trim(),
          rent_reminders_enabled: v.rent_reminders_enabled,
        },
      });
      await qc.invalidateQueries({ queryKey: ["orgs"] });
      toast.show(strings.common.saved);
    } catch (err) {
      form.fromApiError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="max-w-2xl">
      <form onSubmit={submit} noValidate className="space-y-4">
        {!manage && <Banner tone="info">{t.readOnly}</Banner>}
        {form.formError && <Banner tone="error">{form.formError}</Banner>}
        <fieldset disabled={!manage} className="space-y-4">
          <TextField label={strings.orgs.name} required {...form.text("name")} />
          <Select label={strings.orgs.kind} options={optionsFrom(strings.orgs.kinds, ["platform"])} {...form.text("kind")} />
          <PhoneInput label={strings.orgs.phone} optional value={v.phone_number} onChange={(x) => form.set("phone_number", x)} error={form.errors.phone_number} />
          <TextField label={strings.orgs.email} type="email" optional {...form.text("email")} />
          <TextArea label={strings.fields.address} optional rows={2} {...form.text("address")} />
          <Switch
            label={t.reminders}
            hint={t.remindersHint}
            checked={v.rent_reminders_enabled}
            onChange={(x) => form.set("rent_reminders_enabled", x)}
            disabled={!manage}
          />
        </fieldset>
        {manage && (
          <Button type="submit" loading={busy}>
            {strings.common.saveChanges}
          </Button>
        )}
      </form>
    </Card>
  );
}
