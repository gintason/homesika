import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router";

import { Banner, Button, Card, LoadingBlock, PageHeader, Select, TextArea, TextField, optionsFrom, useToast } from "../../components";
import { strings } from "../../i18n";
import { api } from "../../lib/api";
import { useForm } from "../../lib/form";
import { useOrg } from "../../lib/org";
import { useInvalidateOrg, useOrgQuery } from "../../lib/queries";
import type { Property } from "../../lib/types";

const t = strings.properties;

export function PropertyForm() {
  const { propertyId } = useParams();
  const editing = Boolean(propertyId);
  const { org, base } = useOrg();
  const navigate = useNavigate();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const existing = useOrgQuery<Property>(`/properties/${propertyId}/`, undefined, { enabled: editing });
  const [busy, setBusy] = useState(false);
  const form = useForm({ name: "", kind: "block", address: "", city: "", state: "", notes: "" });
  const { setValues } = form;

  useEffect(() => {
    const p = existing.data;
    if (p) setValues({ name: p.name, kind: p.kind, address: p.address, city: p.city, state: p.state, notes: p.notes });
  }, [existing.data, setValues]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const v = form.values;
    if (
      !form.validate({
        name: v.name.trim() ? undefined : strings.common.required,
        address: v.address.trim() ? undefined : strings.common.required,
      })
    )
      return;
    setBusy(true);
    try {
      const saved = await api<Property>(`/orgs/${org.id}/properties/${editing ? `${propertyId}/` : ""}`, {
        method: editing ? "PATCH" : "POST",
        body: { ...v, name: v.name.trim(), address: v.address.trim() },
      });
      await invalidate();
      toast.show(editing ? strings.common.saved : t.created);
      navigate(`${base}/properties/${saved.id}`);
    } catch (err) {
      form.fromApiError(err);
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader
        title={editing ? t.edit : t.add}
        back={{ to: editing ? `${base}/properties/${propertyId}` : `${base}/properties`, label: strings.common.back }}
      />
      {editing && existing.isLoading ? (
        <LoadingBlock />
      ) : editing && existing.error ? (
        <Banner tone="error" onRetry={() => void existing.refetch()}>{strings.errors.loadFailed}</Banner>
      ) : (
        <Card className="max-w-2xl">
          <form onSubmit={submit} noValidate className="space-y-4">
            {form.formError && <Banner tone="error">{form.formError}</Banner>}
            <TextField label={t.name} required {...form.text("name")} />
            <Select label={t.kind} options={optionsFrom(t.kinds)} {...form.text("kind")} />
            <TextField label={strings.fields.address} required {...form.text("address")} />
            <div className="grid gap-4 sm:grid-cols-2">
              <TextField label={t.city} optional {...form.text("city")} />
              <TextField label={t.state} optional {...form.text("state")} />
            </div>
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
