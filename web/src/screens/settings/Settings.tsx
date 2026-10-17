import { useSearchParams } from "react-router";

import { ButtonLink, PageHeader, Tabs } from "../../components";
import { strings } from "../../i18n";
import { useOrg } from "../../lib/org";
import { OrgSettings } from "./OrgSettings";
import { PayoutSettings } from "./PayoutSettings";
import { TeamSettings } from "./TeamSettings";

const t = strings.settings;

export function Settings() {
  const { base, can } = useOrg();
  const [params, setParams] = useSearchParams();
  const items = [
    { id: "organization", label: t.orgTab, content: <OrgSettings /> },
    ...(can("members.view") ? [{ id: "team", label: t.teamTab, content: <TeamSettings /> }] : []),
    ...(can("payment.view") ? [{ id: "payout", label: t.payoutTab, content: <PayoutSettings /> }] : []),
  ];
  return (
    <>
      <PageHeader
        title={t.title}
        actions={
          can("kb.manage") ? (
            <ButtonLink variant="secondary" to={`${base}/settings/help-articles`}>
              {strings.kb.link}
            </ButtonLink>
          ) : undefined
        }
      />
      <Tabs label={t.title} items={items} value={params.get("tab") ?? "organization"} onChange={(id) => setParams({ tab: id }, { replace: true })} />
    </>
  );
}
