import { useState } from "react";
import { useNavigate, useParams } from "react-router";

import {
  Button,
  ButtonLink,
  Card,
  ConfirmDialog,
  DataTable,
  DescriptionList,
  PageHeader,
  StatusBadge,
  useToast,
} from "../../components";
import { strings } from "../../i18n";
import { api, errorText } from "../../lib/api";
import { formatMoney } from "../../lib/money";
import { useOrg } from "../../lib/org";
import { useInvalidateOrg, useOrgQuery } from "../../lib/queries";
import type { Property, Unit } from "../../lib/types";
import { QueryState } from "../shared";
import { UnitDialog } from "./UnitDialog";

const t = strings.properties;
const tu = strings.units;

export function PropertyDetail() {
  const { propertyId = "" } = useParams();
  const { org, base, can } = useOrg();
  const navigate = useNavigate();
  const toast = useToast();
  const invalidate = useInvalidateOrg();
  const property = useOrgQuery<Property>(`/properties/${propertyId}/`);
  const units = useOrgQuery<Unit[]>(`/properties/${propertyId}/units/`);
  const [editing, setEditing] = useState<Unit | "new" | null>(null);
  const [deleting, setDeleting] = useState<{ kind: "property" } | { kind: "unit"; unit: Unit } | null>(null);
  const [busy, setBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const manage = can("property.manage");

  const confirmDelete = async () => {
    if (!deleting) return;
    setBusy(true);
    setDeleteError(null);
    try {
      if (deleting.kind === "property") {
        await api(`/orgs/${org.id}/properties/${propertyId}/`, { method: "DELETE" });
        await invalidate();
        toast.show(strings.common.deleted);
        navigate(`${base}/properties`);
        return;
      }
      await api(`/orgs/${org.id}/properties/${propertyId}/units/${deleting.unit.id}/`, { method: "DELETE" });
      await invalidate();
      toast.show(strings.common.deleted);
      setDeleting(null);
    } catch (err) {
      setDeleteError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <QueryState {...property}>
      {(p) => (
        <>
          <PageHeader
            title={p.name}
            description={t.kinds[p.kind]}
            back={{ to: `${base}/properties`, label: t.title }}
            actions={
              manage && (
                <>
                  <ButtonLink to={`${base}/properties/${p.id}/edit`} variant="secondary">
                    {strings.common.edit}
                  </ButtonLink>
                  <Button variant="ghost" onClick={() => setDeleting({ kind: "property" })}>
                    {strings.common.delete}
                  </Button>
                </>
              )
            }
          />
          <div className="space-y-6">
            <Card>
              <DescriptionList
                items={[
                  { label: strings.fields.address, value: [p.address, p.city, p.state].filter(Boolean).join(", ") },
                  { label: t.units, value: `${p.occupied_count} / ${p.unit_count} ${t.occupied.toLowerCase()}` },
                  { label: strings.fields.notes, value: p.notes },
                ]}
              />
            </Card>
            <Card
              title={tu.title}
              actions={manage && <Button onClick={() => setEditing("new")}>{tu.add}</Button>}
            >
              <DataTable
                caption={tu.title}
                rows={units.data}
                loading={units.isLoading}
                error={units.error}
                onRetry={() => void units.refetch()}
                rowKey={(u) => u.id}
                empty={{ title: tu.empty, body: tu.emptyHint }}
                columns={[
                  { key: "label", header: tu.label, cell: (u) => <span className="font-medium">{u.label}</span> },
                  { key: "kind", header: tu.kind, cell: (u) => tu.kinds[u.kind] },
                  { key: "rent", header: tu.defaultRent, align: "right", cell: (u) => formatMoney(u.default_rent_amount, org.currency) },
                  { key: "status", header: tu.status, cell: (u) => <StatusBadge status={u.status} /> },
                  ...(manage
                    ? [
                        {
                          key: "actions",
                          header: strings.common.actions,
                          hideHeader: true,
                          cell: (u: Unit) => (
                            <div className="flex flex-wrap justify-end gap-2">
                              <Button variant="ghost" onClick={() => setEditing(u)} aria-label={`${strings.common.edit} ${u.label}`}>
                                {strings.common.edit}
                              </Button>
                              <Button
                                variant="ghost"
                                onClick={() => setDeleting({ kind: "unit", unit: u })}
                                aria-label={`${strings.common.delete} ${u.label}`}
                              >
                                {strings.common.delete}
                              </Button>
                            </div>
                          ),
                        },
                      ]
                    : []),
                ]}
              />
            </Card>
          </div>
          {editing && (
            <UnitDialog
              key={editing === "new" ? "new" : editing.id}
              propertyId={p.id}
              unit={editing === "new" ? null : editing}
              onClose={() => setEditing(null)}
            />
          )}
          <ConfirmDialog
            open={deleting !== null}
            onClose={() => {
              setDeleting(null);
              setDeleteError(null);
            }}
            onConfirm={() => void confirmDelete()}
            title={deleting?.kind === "unit" ? tu.deleteTitle : t.deleteTitle}
            description={deleting?.kind === "unit" ? tu.deleteBody : t.deleteBody}
            confirmLabel={strings.common.delete}
            destructive
            loading={busy}
            error={deleteError}
          />
        </>
      )}
    </QueryState>
  );
}
