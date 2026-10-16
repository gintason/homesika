import { useEffect, useMemo } from "react";
import { Outlet, useNavigate, useParams } from "react-router";

import { AppShell, Banner, EmptyState, ButtonLink, LoadingBlock, type NavItem } from "../../components";
import { strings } from "../../i18n";
import { errorText } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { lastOrg, makeOrgContext, OrgContext, useMyOrgs } from "../../lib/org";
import type { Capability } from "../../lib/permissions";

const NAV: Array<{ path: string; label: string; cap: Capability }> = [
  { path: "dashboard", label: strings.nav.dashboard, cap: "org.view" },
  { path: "properties", label: strings.nav.properties, cap: "property.view" },
  { path: "tenants", label: strings.nav.tenants, cap: "tenant.view" },
  { path: "leases", label: strings.nav.leases, cap: "tenant.view" },
  { path: "charges", label: strings.nav.charges, cap: "tenant.view" },
  { path: "arrears", label: strings.nav.arrears, cap: "tenant.view" },
  { path: "payments", label: strings.nav.payments, cap: "payment.view" },
  { path: "payment-links", label: strings.nav.paymentLinks, cap: "payment.view" },
  { path: "expenses", label: strings.nav.expenses, cap: "expense.view" },
  { path: "statement", label: strings.nav.statement, cap: "report.view" },
  { path: "settings", label: strings.nav.settings, cap: "org.view" },
];

/** Resolves /orgs/:orgId against my organizations and provides OrgContext + the app shell. */
export function OrgLayout() {
  const { orgId = "" } = useParams();
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const { data: orgs, error, isLoading, refetch } = useMyOrgs();

  const ctx = useMemo(() => {
    const org = orgs?.find((o) => o.id === orgId);
    return org && orgs ? makeOrgContext(org, orgs) : null;
  }, [orgs, orgId]);

  useEffect(() => {
    if (ctx) lastOrg.set(ctx.org.id);
  }, [ctx]);

  if (isLoading) {
    return (
      <div className="mx-auto max-w-[1120px] px-5 py-8">
        <LoadingBlock />
      </div>
    );
  }
  if (error || !orgs) {
    return (
      <div className="mx-auto max-w-md px-5 py-16">
        <Banner tone="error" title={strings.errors.loadFailed} onRetry={() => void refetch()}>
          {errorText(error)}
        </Banner>
      </div>
    );
  }
  if (!ctx) {
    return (
      <div className="mx-auto max-w-xl px-5 py-16">
        <EmptyState title={strings.errors.notFound} body={strings.orgs.notFound} action={<ButtonLink to="/">{strings.notFound.home}</ButtonLink>} />
      </div>
    );
  }

  const nav: NavItem[] = NAV.filter((n) => ctx.can(n.cap)).map((n) => ({ to: `${ctx.base}/${n.path}`, label: n.label }));

  return (
    <OrgContext.Provider value={ctx}>
      <AppShell
        nav={nav}
        orgs={orgs.map((o) => ({ id: o.id, name: o.name }))}
        currentOrgId={ctx.org.id}
        createOrgHref="/orgs/new"
        onSwitchOrg={(idOrHref) => navigate(idOrHref.startsWith("/") ? idOrHref : `/orgs/${idOrHref}/dashboard`)}
        userName={user ? `${user.first_name} ${user.last_name}`.trim() : ""}
        onSignOut={() => {
          void signOut().then(() => navigate("/signin", { replace: true }));
        }}
      >
        <Outlet />
      </AppShell>
    </OrgContext.Provider>
  );
}
