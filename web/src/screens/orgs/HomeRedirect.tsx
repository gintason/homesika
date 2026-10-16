import { Navigate } from "react-router";

import { Banner, LoadingBlock } from "../../components";
import { strings } from "../../i18n";
import { errorText } from "../../lib/api";
import { lastOrg, useMyOrgs } from "../../lib/org";

/** "/" -> the last organization used, else the first, else first-run "create organization". */
export function HomeRedirect() {
  const { data, error, isLoading, refetch } = useMyOrgs();
  if (isLoading) {
    return (
      <div className="mx-auto max-w-md px-5 py-16">
        <LoadingBlock rows={3} />
      </div>
    );
  }
  if (error || !data) {
    return (
      <div className="mx-auto max-w-md px-5 py-16">
        <Banner tone="error" title={strings.errors.loadFailed} onRetry={() => void refetch()}>
          {errorText(error)}
        </Banner>
      </div>
    );
  }
  if (data.length === 0) return <Navigate to="/orgs/new" replace />;
  const remembered = lastOrg.get();
  const org = data.find((o) => o.id === remembered) ?? data[0];
  return <Navigate to={`/orgs/${org?.id}/dashboard`} replace />;
}
