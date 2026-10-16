import { useState } from "react";
import { useNavigate, useParams } from "react-router";

import { Button, ButtonLink, Card, ConfirmDialog, DescriptionList, PageHeader, Tabs, useToast } from "../../components";
import { strings } from "../../i18n";
import { api, errorText } from "../../lib/api";
import { useOrg } from "../../lib/org";
import { formatPhone } from "../../lib/phone";
import { useInvalidateOrg, useOrgQuery } from "../../lib/queries";
import type { Tenant } from "../../lib/types";
import { QueryState } from "../shared";
import { ChargesTable, LeasesTable, PaymentsTable } from "../tables";

const t = strings.tenants;

export function TenantDetail() {
  const { tenantId = "" } = useParams();
  const { org, base, can } = useOrg();
  const navigate = useNavigate();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const q = useOrgQuery<Tenant>(`/tenants/${tenantId}/`);
  const [tab, setTab] = useState("leases");
  const [deleting, setDeleting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const remove = async () => {
    setBusy(true);
    setError(null);
    try {
      await api(`/orgs/${org.id}/tenants/${tenantId}/`, { method: "DELETE" });
      await invalidate();
      toast.show(strings.common.deleted);
      navigate(`${base}/tenants`);
    } catch (err) {
      setError(errorText(err));
      setBusy(false);
    }
  };

  const tabs = [
    { id: "leases", label: t.leasesTab, content: <LeasesTable query={{ tenant: tenantId }} showTenant={false} /> },
    { id: "charges", label: t.chargesTab, content: <ChargesTable query={{ tenant: tenantId }} showTenant={false} /> },
    ...(can("payment.view")
      ? [{ id: "payments", label: t.paymentsTab, content: <PaymentsTable query={{ tenant: tenantId }} showTenant={false} /> }]
      : []),
  ];

  return (
    <QueryState {...q}>
      {(x) => (
        <>
          <PageHeader
            title={x.full_name}
            description={formatPhone(x.phone_number)}
            back={{ to: `${base}/tenants`, label: t.title }}
            actions={
              <>
                {can("payment.record") && <ButtonLink to={`${base}/payments/new?tenant=${x.id}`}>{strings.dashboard.recordPayment}</ButtonLink>}
                {can("payment.link") && (
                  <ButtonLink to={`${base}/payment-links/new?tenant=${x.id}`} variant="secondary">
                    {strings.dashboard.sendLink}
                  </ButtonLink>
                )}
                {can("lease.manage") && (
                  <ButtonLink to={`${base}/leases/new?tenant=${x.id}`} variant="secondary">
                    {t.newLease}
                  </ButtonLink>
                )}
                {can("tenant.manage") && (
                  <ButtonLink to={`${base}/tenants/${x.id}/edit`} variant="ghost">
                    {strings.common.edit}
                  </ButtonLink>
                )}
                {can("tenant.manage") && (
                  <Button variant="ghost" onClick={() => setDeleting(true)}>
                    {strings.common.delete}
                  </Button>
                )}
              </>
            }
          />
          <div className="space-y-6">
            <Card>
              <DescriptionList
                items={[
                  { label: t.activeLease, value: x.active_lease ? `${x.active_lease.property} · ${x.active_lease.unit}` : t.noLease },
                  { label: strings.fields.email, value: x.email },
                  { label: t.occupation, value: x.occupation },
                  { label: t.nextOfKin, value: x.next_of_kin },
                  { label: t.idDocument, value: x.id_document },
                  { label: t.hasApp, value: x.has_app ? strings.common.yes : strings.common.no },
                  { label: strings.fields.notes, value: x.notes },
                ]}
              />
            </Card>
            <Tabs label={x.full_name} items={tabs} value={tab} onChange={setTab} />
          </div>
          <ConfirmDialog
            open={deleting}
            onClose={() => {
              setDeleting(false);
              setError(null);
            }}
            onConfirm={() => void remove()}
            title={t.deleteTitle}
            description={t.deleteBody}
            confirmLabel={strings.common.delete}
            destructive
            loading={busy}
            error={error}
          />
        </>
      )}
    </QueryState>
  );
}
