import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";

import { Banner, Button, Card, PageHeader, Select, TextArea, TextField, useToast } from "../../components";
import { strings } from "../../i18n";
import { ApiError, api } from "../../lib/api";
import { useIdempotencyKey } from "../../lib/idempotency";
import { useOrg } from "../../lib/org";
import { useInvalidateOrg, useOrgQuery } from "../../lib/queries";
import type { Ticket, TicketPriority, Trade, Unit } from "../../lib/types";
import { actionError } from "../shared";

const t = strings.repairs;

/** Staff log a repair they've spotted themselves (approved straight away). */
export function NewRepair() {
  const { org, base } = useOrg();
  const navigate = useNavigate();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const idem = useIdempotencyKey();
  const units = useOrgQuery<Unit[]>("/units/");
  const [form, setForm] = useState({
    unit: "",
    category: "plumbing" as Trade,
    priority: "normal" as TicketPriority,
    title: "",
    description: "",
    access_notes: "",
  });
  const [fields, setFields] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setFields({});
    try {
      const body = { ...form, title: form.title.trim(), description: form.description.trim() };
      const created = await api<Ticket>(`/orgs/${org.id}/tickets/`, { method: "POST", body, idempotencyKey: idem.keyFor(body) });
      idem.reset();
      await invalidate();
      toast.show(t.created);
      navigate(`${base}/repairs/${created.id}`);
    } catch (err) {
      if (err instanceof ApiError) setFields(err.fieldErrors);
      setError(actionError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader back={{ to: `${base}/repairs`, label: t.title }} title={t.newTitle} description={t.newIntro} />
      <Card className="max-w-2xl">
        <form className="space-y-4" onSubmit={(e) => void submit(e)} noValidate>
          {error && <Banner tone="error">{error}</Banner>}
          <Select
            label={t.chooseUnit}
            value={form.unit}
            placeholder={units.isLoading ? strings.app.loading : " "}
            options={(units.data ?? []).map((u) => ({ value: u.id, label: `${u.label}, ${u.property_name}` }))}
            onChange={set("unit")}
            error={fields.unit}
            required
          />
          <div className="grid gap-4 sm:grid-cols-2">
            <Select
              label={t.category}
              value={form.category}
              options={Object.entries(t.categories).map(([value, label]) => ({ value, label }))}
              onChange={set("category")}
            />
            <Select
              label={t.priority}
              value={form.priority}
              options={Object.entries(t.priorities).map(([value, label]) => ({ value, label }))}
              onChange={set("priority")}
            />
          </div>
          <TextField label={t.titleLabel} hint={t.titleHint} value={form.title} maxLength={120} onChange={set("title")} error={fields.title} required />
          <TextArea label={t.descriptionLabel} value={form.description} rows={4} maxLength={2000} onChange={set("description")} error={fields.description} required />
          <TextField label={t.accessLabel} hint={t.accessHint} optional value={form.access_notes} maxLength={200} onChange={set("access_notes")} />
          <Button type="submit" loading={busy} disabled={!form.unit}>
            {t.create}
          </Button>
        </form>
      </Card>
    </>
  );
}
