import { useState, type FormEvent } from "react";

import { Banner, Button, Card, ConfirmDialog, EmptyState, LoadingBlock, TextField, useToast } from "../../components";
import { fmt, strings } from "../../i18n";
import { api } from "../../lib/api";
import { formatDateTime, localInputToISO } from "../../lib/dates";
import { useForm } from "../../lib/form";
import { useOrg } from "../../lib/org";
import { useInvalidateOrg, useOrgQuery } from "../../lib/queries";
import type { ViewingSlot } from "../../lib/types";
import { actionError } from "../shared";

const t = strings.slots;

function plusMinutes(local: string, minutes: number): string {
  const d = new Date(local);
  if (Number.isNaN(d.getTime())) return "";
  d.setMinutes(d.getMinutes() + minutes);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Viewing slots for one listing (viewing-slots/?listing=): add, list with booked count, delete. */
export function ViewingSlots({ listingId }: { listingId: string }) {
  const { org, can } = useOrg();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const canManage = can("listing.manage");
  const q = useOrgQuery<ViewingSlot[]>("/viewing-slots/", { listing: listingId });
  const form = useForm({ starts_at: "", ends_at: "", capacity: "1" });
  const [busy, setBusy] = useState(false);
  const [deleting, setDeleting] = useState<ViewingSlot | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const v = form.values;
    const start = localInputToISO(v.starts_at);
    const end = localInputToISO(v.ends_at);
    const cap = Number(v.capacity);
    if (
      !form.validate({
        starts_at: start ? undefined : strings.common.required,
        ends_at: !end ? strings.common.required : start && end <= start ? t.endBeforeStart : undefined,
        capacity: Number.isInteger(cap) && cap >= 1 ? undefined : strings.listings.wholeNumber,
      })
    )
      return;
    setBusy(true);
    try {
      await api(`/orgs/${org.id}/viewing-slots/`, {
        method: "POST",
        body: { listing: listingId, starts_at: start, ends_at: end, capacity: cap },
      });
      await invalidate();
      toast.show(t.added);
      form.setValues({ starts_at: "", ends_at: "", capacity: v.capacity });
    } catch (err) {
      form.fromApiError(err);
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!deleting) return;
    setDeleteBusy(true);
    setDeleteError(null);
    try {
      await api(`/orgs/${org.id}/viewing-slots/${deleting.id}/`, { method: "DELETE" });
      await invalidate();
      toast.show(strings.common.deleted);
      setDeleting(null);
    } catch (err) {
      setDeleteError(actionError(err));
    } finally {
      setDeleteBusy(false);
    }
  };

  return (
    <Card title={t.title}>
      <div className="space-y-4">
        <p className="text-base text-ink-600">{t.intro}</p>
        {q.isLoading ? (
          <LoadingBlock rows={2} />
        ) : q.error ? (
          <Banner tone="error" title={strings.errors.loadFailed} onRetry={() => void q.refetch()} />
        ) : !q.data?.length ? (
          <EmptyState title={t.empty} body={canManage ? t.emptyHint : undefined} />
        ) : (
          <ul className="divide-y divide-surface-line" aria-label={t.title}>
            {q.data.map((s) => (
              <li key={s.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div>
                  <p className="font-medium text-ink-800">
                    {formatDateTime(s.starts_at)} – {formatDateTime(s.ends_at)}
                  </p>
                  <p className="text-sm text-ink-600">
                    {t.booked}: {fmt(t.bookedOf, { booked: s.booked, capacity: s.capacity })}
                  </p>
                </div>
                {canManage && (
                  <Button variant="ghost" onClick={() => setDeleting(s)} aria-label={fmt(t.deleteLabel, { when: formatDateTime(s.starts_at) })}>
                    {strings.common.delete}
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
        {canManage && (
          <form onSubmit={submit} noValidate className="space-y-4 border-t border-surface-line pt-4">
            {form.formError && <Banner tone="error">{form.formError}</Banner>}
            <div className="grid gap-4 sm:grid-cols-3">
              <TextField
                label={t.starts}
                type="datetime-local"
                {...form.text("starts_at")}
                onChange={(e) => {
                  const value = e.target.value;
                  form.set("starts_at", value);
                  if (!form.values.ends_at && value) form.set("ends_at", plusMinutes(value, 30));
                }}
              />
              <TextField label={t.ends} type="datetime-local" {...form.text("ends_at")} />
              <TextField label={t.capacity} type="number" min={1} max={50} inputMode="numeric" {...form.text("capacity")} />
            </div>
            <Button type="submit" variant="secondary" loading={busy}>
              {t.add}
            </Button>
          </form>
        )}
      </div>
      <ConfirmDialog
        open={deleting !== null}
        onClose={() => {
          setDeleting(null);
          setDeleteError(null);
        }}
        onConfirm={() => void remove()}
        title={t.deleteTitle}
        description={t.deleteBody}
        confirmLabel={strings.common.delete}
        destructive
        loading={deleteBusy}
        error={deleteError}
      />
    </Card>
  );
}
