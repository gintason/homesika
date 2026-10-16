import { Link } from "react-router";

import { ButtonLink, DataTable, PageHeader } from "../../components";
import { fmt, strings } from "../../i18n";
import { useOrg } from "../../lib/org";
import { useOrgQuery } from "../../lib/queries";
import type { Property } from "../../lib/types";
import { linkClass } from "../shared";

const t = strings.properties;

export function PropertiesList() {
  const { base, can } = useOrg();
  const q = useOrgQuery<Property[]>("/properties/");
  const add = can("property.manage") ? <ButtonLink to={`${base}/properties/new`}>{t.add}</ButtonLink> : undefined;
  return (
    <>
      <PageHeader title={t.title} actions={add} />
      <DataTable
        caption={t.title}
        rows={q.data}
        loading={q.isLoading}
        error={q.error}
        onRetry={() => void q.refetch()}
        rowKey={(p) => p.id}
        empty={{ title: t.empty, body: t.emptyHint, action: add }}
        columns={[
          {
            key: "name",
            header: t.name,
            cell: (p) => (
              <Link to={`${base}/properties/${p.id}`} className={linkClass}>
                {p.name}
              </Link>
            ),
          },
          { key: "kind", header: t.kind, cell: (p) => t.kinds[p.kind] ?? p.kind },
          { key: "address", header: strings.fields.address, cell: (p) => [p.address, p.city].filter(Boolean).join(", ") },
          {
            key: "units",
            header: t.units,
            cell: (p) => fmt(t.unitsSummary, { occupied: p.occupied_count, total: p.unit_count }),
          },
        ]}
      />
    </>
  );
}
