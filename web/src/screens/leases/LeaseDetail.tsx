import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { Banner, Button, Card, Checkbox, ConfirmDialog, DescriptionList, PageHeader, StatusBadge, TextField, useToast } from "../../components";
import { strings } from "../../i18n";
import { api, errorText } from "../../lib/api";
import { formatDate, todayISO } from "../../lib/dates";
import { formatMoney } from "../../lib/money";
import { useOrg } from "../../lib/org";
import { useInvalidateOrg, useOrgQuery } from "../../lib/queries";
import type { Lease } from "../../lib/types";
import { QueryState, linkClass } from "../shared";
import { ChargesTable } from "../tables";

const t = strings.leases;

type Action = "activate" | "end" | "delete" | null;

export function LeaseDetail() {
  const { leaseId = "" } = useParams();
  const { org, base, can } = useOrg();
  const navigate = useNavigate();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const q = useOrgQuery<Lease>(`/leases/${leaseId}/`);
  const [action, setAction] = useState<Action>(null);
  const [endedOn, setEndedOn] = useState(todayISO());
  const [terminated, setTerminated] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const manage = can("lease.manage");

  const close = () => {
    setAction(null);
    setError(null);
  };

  const run = async () => {
    setBusy(true);
    setError(null);
    const path = `/orgs/${org.id}/leases/${leaseId}/`;
    try {
      if (action === "activate") {
        await api(`${path}activate/`, { method: "POST" });
        toast.show(t.activated);
      } else if (action === "end") {
        await api(`${path}end/`, { method: "POST", body: { ended_on: endedOn, terminated } });
        toast.show(t.ended);
      } else if (action === "delete") {
        await api(path, { method: "DELETE" });
        await invalidate();
        toast.show(strings.common.deleted);
        navigate(`${base}/leases`);
        return;
      }
      await invalidate();
      close();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <QueryState {...q}>
      {(l) => (
        <>
          <PageHeader
            title={`${l.property_name} · ${l.unit_label}`}
            description={
              <span className="flex flex-wrap items-center gap-2">
                <Link to={`${base}/tenants/${l.tenant}`} className={linkClass}>
                  {l.tenant_name}
                </Link>
                <StatusBadge status={l.status} />
              </span>
            }
            back={{ to: `${base}/leases`, label: t.title }}
            actions={
              manage && (
                <>
                  {l.status === "draft" && <Button onClick={() => setAction("activate")}>{t.activate}</Button>}
                  {l.status === "draft" && (
                    <Button variant="ghost" onClick={() => setAction("delete")}>
                      {t.deleteDraft}
                    </Button>
                  )}
                  {l.status === "active" && (
                    <Button variant="secondary" onClick={() => setAction("end")}>
                      {t.end}
                    </Button>
                  )}
                </>
              )
            }
          />
          <div className="space-y-6">
            {l.status === "draft" && <Banner tone="warning">{t.draftNote}</Banner>}
            <Card>
              <DescriptionList
                items={[
                  { label: t.startDate, value: formatDate(l.start_date) },
                  { label: t.endDate, value: formatDate(l.end_date) },
                  { label: t.rentAmount, value: `${formatMoney(l.rent_amount, l.currency)} (${t.frequencies[l.rent_frequency]})` },
                  { label: t.serviceCharge, value: formatMoney(l.service_charge_amount, l.currency) },
                  { label: t.deposit, value: formatMoney(l.deposit_amount, l.currency) },
                  { label: t.balance, value: formatMoney(l.balance ?? "0.00", l.currency) },
                  l.ended_on ? { label: t.endedOn, value: formatDate(l.ended_on) } : null,
                  { label: strings.fields.notes, value: l.notes },
                ]}
              />
            </Card>
            {l.status !== "draft" && (
              <Card title={t.charges}>
                <ChargesTable query={{ lease: l.id }} showTenant={false} />
              </Card>
            )}
          </div>
          <ConfirmDialog
            open={action === "activate"}
            onClose={close}
            onConfirm={() => void run()}
            title={t.activateTitle}
            description={t.activateBody}
            confirmLabel={t.activate}
            loading={busy}
            error={error}
          />
          <ConfirmDialog
            open={action === "delete"}
            onClose={close}
            onConfirm={() => void run()}
            title={t.deleteTitle}
            confirmLabel={strings.common.delete}
            destructive
            loading={busy}
            error={error}
          />
          <ConfirmDialog
            open={action === "end"}
            onClose={close}
            onConfirm={() => void run()}
            title={t.endTitle}
            description={t.endBody}
            confirmLabel={t.end}
            destructive
            loading={busy}
            error={error}
            confirmDisabled={!endedOn}
          >
            <TextField label={t.endedOn} type="date" value={endedOn} onChange={(e) => setEndedOn(e.target.value)} />
            <Checkbox label={t.terminated} checked={terminated} onChange={(e) => setTerminated(e.target.checked)} />
          </ConfirmDialog>
        </>
      )}
    </QueryState>
  );
}
