import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router";

import { Banner, Button, Card, LoadingBlock, PageHeader, PhoneInput, TextArea, TextField, useToast } from "../../components";
import { strings } from "../../i18n";
import { api } from "../../lib/api";
import { useForm } from "../../lib/form";
import { useOrg } from "../../lib/org";
import { formatPhone, isValidNigerianPhone, normalisePhone } from "../../lib/phone";
import { useInvalidateOrg, useOrgQuery } from "../../lib/queries";
import type { Tenant } from "../../lib/types";

const t = strings.tenants;

export function TenantForm() {
  const { tenantId } = useParams();
  const editing = Boolean(tenantId);
  const { org, base } = useOrg();
  const navigate = useNavigate();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const existing = useOrgQuery<Tenant>(`/tenants/${tenantId}/`, undefined, { enabled: editing });
  const [busy, setBusy] = useState(false);
  const form = useForm({ full_name: "", phone_number: "", email: "", occupation: "", next_of_kin: "", id_document: "", notes: "" });
  const { setValues } = form;

  useEffect(() => {
    const x = existing.data;
    if (x)
      setValues({
        full_name: x.full_name,
        phone_number: formatPhone(x.phone_number),
        email: x.email,
        occupation: x.occupation,
        next_of_kin: x.next_of_kin,
        id_document: x.id_document,
        notes: x.notes,
      });
  }, [existing.data, setValues]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const v = form.values;
    if (
      !form.validate({
        full_name: v.full_name.trim() ? undefined : strings.common.required,
        phone_number: isValidNigerianPhone(v.phone_number) ? undefined : strings.fields.phoneInvalid,
        email: !v.email || /^\S+@\S+\.\S+$/.test(v.email) ? undefined : strings.fields.emailInvalid,
      })
    )
      return;
    setBusy(true);
    try {
      const saved = await api<Tenant>(`/orgs/${org.id}/tenants/${editing ? `${tenantId}/` : ""}`, {
        method: editing ? "PATCH" : "POST",
        body: { ...v, full_name: v.full_name.trim(), phone_number: normalisePhone(v.phone_number), email: v.email.trim() },
      });
      await invalidate();
      toast.show(editing ? strings.common.saved : t.created);
      navigate(`${base}/tenants/${saved.id}`);
    } catch (err) {
      form.fromApiError(err);
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader
        title={editing ? t.edit : t.add}
        back={{ to: editing ? `${base}/tenants/${tenantId}` : `${base}/tenants`, label: strings.common.back }}
      />
      {editing && existing.isLoading ? (
        <LoadingBlock />
      ) : editing && existing.error ? (
        <Banner tone="error" onRetry={() => void existing.refetch()}>{strings.errors.loadFailed}</Banner>
      ) : (
        <Card className="max-w-2xl">
          <form onSubmit={submit} noValidate className="space-y-4">
            {form.formError && <Banner tone="error">{form.formError}</Banner>}
            <TextField label={t.fullName} required autoComplete="off" {...form.text("full_name")} />
            <PhoneInput value={form.values.phone_number} onChange={(x) => form.set("phone_number", x)} error={form.errors.phone_number} required />
            <TextField label={strings.fields.email} type="email" optional {...form.text("email")} />
            <TextField label={t.occupation} optional {...form.text("occupation")} />
            <TextField label={t.nextOfKin} hint={t.nextOfKinHint} optional {...form.text("next_of_kin")} />
            <TextField label={t.idDocument} hint={t.idDocumentHint} optional {...form.text("id_document")} />
            <TextArea label={strings.fields.notes} optional {...form.text("notes")} />
            <Button type="submit" loading={busy}>
              {editing ? strings.common.saveChanges : t.add}
            </Button>
          </form>
        </Card>
      )}
    </>
  );
}
