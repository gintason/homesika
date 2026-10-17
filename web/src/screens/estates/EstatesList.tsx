import { useState } from "react";
import { Link, useNavigate } from "react-router";

import { Button, DataTable, Dialog, PageHeader, TextArea, TextField, useToast } from "../../components";
import { strings } from "../../i18n";
import { api } from "../../lib/api";
import { useOrg } from "../../lib/org";
import { useInvalidateOrg, usePaginatedList } from "../../lib/queries";
import type { Estate } from "../../lib/types";
import { actionError, linkClass } from "../shared";

const t = strings.estates;

/** "A1, A2\nB1" -> ["A1", "A2", "B1"] */
export function splitHouses(text: string): string[] {
  return [...new Set(text.split(/[\n,]+/).map((s) => s.trim()).filter(Boolean))];
}

export function EstatesList() {
  const { base, can } = useOrg();
  const list = usePaginatedList<Estate>("/estates/");
  const [open, setOpen] = useState(false);
  return (
    <>
      <PageHeader
        title={t.title}
        description={t.intro}
        actions={can("estate.manage") ? <Button onClick={() => setOpen(true)}>{t.add}</Button> : undefined}
      />
      <DataTable
        caption={t.title}
        rows={list.rows}
        loading={list.isLoading}
        error={list.error}
        onRetry={list.refetch}
        hasMore={list.hasMore}
        onLoadMore={list.loadMore}
        loadingMore={list.loadingMore}
        rowKey={(r) => r.id}
        empty={{ title: t.empty, body: t.emptyHint }}
        columns={[
          {
            key: "name",
            header: t.name,
            cell: (r) => (
              <Link to={`${base}/estates/${r.id}`} className={linkClass}>
                {r.name}
              </Link>
            ),
          },
          { key: "houses", header: t.houses, cell: (r) => r.houses },
          { key: "residents", header: t.residents, cell: (r) => r.verified_residents },
          { key: "pending", header: t.pending, cell: (r) => r.pending_residents },
          { key: "code", header: t.joinCode, cell: (r) => <span className="font-mono">{r.join_code}</span> },
        ]}
      />
      <NewEstateDialog open={open} onClose={() => setOpen(false)} />
    </>
  );
}

function NewEstateDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { org, base } = useOrg();
  const navigate = useNavigate();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const [form, setForm] = useState({ name: "", address: "", city: "", state: "", houses: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });

  const submit = async () => {
    const missing: Record<string, string> = {};
    if (!form.name.trim()) missing.name = strings.common.required;
    if (!form.address.trim()) missing.address = strings.common.required;
    setErrors(missing);
    if (Object.keys(missing).length) return;
    setBusy(true);
    setError(null);
    try {
      const estate = await api<Estate>(`/orgs/${org.id}/estates/`, {
        method: "POST",
        body: { ...form, houses: splitHouses(form.houses) },
      });
      await invalidate();
      toast.show(t.created);
      onClose();
      navigate(`${base}/estates/${estate.id}`);
    } catch (err) {
      setError(actionError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={t.add}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {strings.common.cancel}
          </Button>
          <Button onClick={() => void submit()} loading={busy}>
            {strings.common.create}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {error && <p className="text-sm text-danger-700">{error}</p>}
        <TextField label={t.name} value={form.name} onChange={set("name")} error={errors.name} />
        <TextField label={t.address} value={form.address} onChange={set("address")} error={errors.address} />
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField label={t.city} optional value={form.city} onChange={set("city")} />
          <TextField label={t.state} optional value={form.state} onChange={set("state")} />
        </div>
        <TextArea label={t.housesField} hint={t.housesHint} optional rows={4} value={form.houses} onChange={set("houses")} />
      </div>
    </Dialog>
  );
}
