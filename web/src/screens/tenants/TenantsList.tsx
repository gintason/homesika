import { useEffect, useState } from "react";
import { Link } from "react-router";

import { ButtonLink, DataTable, PageHeader, TextField } from "../../components";
import { strings } from "../../i18n";
import { useOrg } from "../../lib/org";
import { formatPhone } from "../../lib/phone";
import { useOrgQuery } from "../../lib/queries";
import type { Tenant } from "../../lib/types";
import { linkClass } from "../shared";

const t = strings.tenants;

export function TenantsList() {
  const { base, can } = useOrg();
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  useEffect(() => {
    const id = window.setTimeout(() => setQ(search.trim()), 300);
    return () => window.clearTimeout(id);
  }, [search]);
  const list = useOrgQuery<Tenant[]>("/tenants/", { q });
  const add = can("tenant.manage") ? <ButtonLink to={`${base}/tenants/new`}>{t.add}</ButtonLink> : undefined;
  return (
    <>
      <PageHeader title={t.title} actions={add} />
      <div className="mb-4 max-w-md">
        <TextField label={t.searchLabel} type="search" value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>
      <DataTable
        caption={t.title}
        rows={list.data}
        loading={list.isLoading}
        error={list.error}
        onRetry={() => void list.refetch()}
        rowKey={(x) => x.id}
        empty={{ title: t.empty, body: q ? undefined : t.emptyHint, action: q ? undefined : add }}
        columns={[
          {
            key: "name",
            header: t.fullName,
            cell: (x) => (
              <Link to={`${base}/tenants/${x.id}`} className={linkClass}>
                {x.full_name}
              </Link>
            ),
          },
          { key: "phone", header: strings.fields.phone, cell: (x) => formatPhone(x.phone_number) },
          {
            key: "home",
            header: t.activeLease,
            cell: (x) => (x.active_lease ? `${x.active_lease.property} · ${x.active_lease.unit}` : t.noLease),
          },
          { key: "app", header: t.hasApp, cell: (x) => (x.has_app ? strings.common.yes : strings.common.no) },
        ]}
      />
    </>
  );
}
