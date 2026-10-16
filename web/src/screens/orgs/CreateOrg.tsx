import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";

import { Banner, Button, Logo, PhoneInput, Select, TextArea, TextField, optionsFrom } from "../../components";
import { strings } from "../../i18n";
import { api } from "../../lib/api";
import { useForm } from "../../lib/form";
import { useMyOrgs } from "../../lib/org";
import { isValidNigerianPhone, normalisePhone } from "../../lib/phone";
import type { Organization } from "../../lib/types";

const t = strings.orgs;

export function CreateOrg() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data: orgs } = useMyOrgs();
  const [busy, setBusy] = useState(false);
  const form = useForm({ name: "", kind: "landlord", phone_number: "", email: "", address: "" });
  const v = form.values;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const ok = form.validate({
      name: v.name.trim() ? undefined : strings.common.required,
      phone_number: !v.phone_number || isValidNigerianPhone(v.phone_number) ? undefined : strings.fields.phoneInvalid,
    });
    if (!ok) return;
    setBusy(true);
    try {
      const org = await api<Organization>("/orgs/", {
        method: "POST",
        body: {
          name: v.name.trim(),
          kind: v.kind,
          phone_number: v.phone_number ? normalisePhone(v.phone_number) : "",
          email: v.email.trim(),
          address: v.address.trim(),
        },
      });
      await qc.invalidateQueries({ queryKey: ["orgs"] });
      navigate(`/orgs/${org.id}/dashboard`, { replace: true });
    } catch (err) {
      form.fromApiError(err);
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-surface-background">
      <header className="bg-primary-800 px-5 py-3">
        <div className="mx-auto flex max-w-xl items-center justify-between">
          <Logo inverse />
          {orgs && orgs.length > 0 && (
            <Link to="/" className="min-h-touch content-center px-2 text-base font-medium text-white underline underline-offset-4">
              {strings.common.cancel}
            </Link>
          )}
        </div>
      </header>
      <main className="mx-auto max-w-xl px-5 py-8">
        <div className="rounded-lg bg-surface-card p-6 shadow-md ring-1 ring-surface-line">
          <h1 className="font-display text-2xl font-bold text-primary-800">{t.createTitle}</h1>
          <p className="mt-2 text-base text-ink-600">{t.createIntro}</p>
          <form onSubmit={submit} noValidate className="mt-6 space-y-4">
            {form.formError && <Banner tone="error">{form.formError}</Banner>}
            <TextField label={t.name} hint={t.nameHint} required autoFocus {...form.text("name")} />
            <Select label={t.kind} options={optionsFrom(t.kinds, ["platform"])} {...form.text("kind")} />
            <PhoneInput
              label={t.phone}
              optional
              value={v.phone_number}
              onChange={(x) => form.set("phone_number", x)}
              error={form.errors.phone_number}
            />
            <TextField label={t.email} type="email" optional {...form.text("email")} />
            <TextArea label={strings.fields.address} optional rows={2} {...form.text("address")} />
            <Button type="submit" fullWidth loading={busy}>
              {strings.common.create}
            </Button>
          </form>
        </div>
      </main>
    </div>
  );
}
