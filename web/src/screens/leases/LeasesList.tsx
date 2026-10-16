import { useState } from "react";

import { ButtonLink, PageHeader, Select, optionsFrom } from "../../components";
import { strings } from "../../i18n";
import { useOrg } from "../../lib/org";
import { LeasesTable } from "../tables";

const t = strings.leases;

export function LeasesList() {
  const { base, can } = useOrg();
  const [status, setStatus] = useState("");
  return (
    <>
      <PageHeader title={t.title} actions={can("lease.manage") && <ButtonLink to={`${base}/leases/new`}>{t.new}</ButtonLink>} />
      <div className="mb-4 max-w-xs">
        <Select
          label={t.status}
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          placeholder={strings.common.all}
          options={optionsFrom(t.statuses)}
        />
      </div>
      <LeasesTable query={{ status }} />
    </>
  );
}
