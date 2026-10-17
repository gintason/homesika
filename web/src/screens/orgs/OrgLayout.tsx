import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Outlet, useNavigate, useParams } from "react-router";

import { AppShell, Banner, EmptyState, ButtonLink, LoadingBlock, type NavItem } from "../../components";
import { fmt, strings } from "../../i18n";
import { api, errorText } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { lastOrg, makeOrgContext, OrgContext, useMyOrgs } from "../../lib/org";
import type { Capability } from "../../lib/permissions";
import { orgKey } from "../../lib/queries";
import type { Conversation, Paginated } from "../../lib/types";
import { AssistantPanel } from "../assistant/AssistantPanel";

const NAV: Array<{ path: string; label: string; cap: Capability }> = [
  { path: "dashboard", label: strings.nav.dashboard, cap: "org.view" },
  { path: "properties", label: strings.nav.properties, cap: "property.view" },
  { path: "tenants", label: strings.nav.tenants, cap: "tenant.view" },
  { path: "leases", label: strings.nav.leases, cap: "tenant.view" },
  { path: "charges", label: strings.nav.charges, cap: "tenant.view" },
  { path: "arrears", label: strings.nav.arrears, cap: "tenant.view" },
  { path: "payments", label: strings.nav.payments, cap: "payment.view" },
  { path: "payment-links", label: strings.nav.paymentLinks, cap: "payment.view" },
  { path: "inbox", label: strings.nav.inbox, cap: "inbox.view" },
  { path: "repairs", label: strings.nav.repairs, cap: "maintenance.view" },
  { path: "estates", label: strings.nav.estates, cap: "estate.view" },
  { path: "security", label: strings.nav.security, cap: "security.view" },
  { path: "gate", label: strings.nav.gate, cap: "gate.verify" },
  { path: "listings", label: strings.nav.listings, cap: "listing.view" },
  { path: "leads", label: strings.nav.leads, cap: "listing.view" },
  { path: "viewings", label: strings.nav.viewings, cap: "listing.view" },
  { path: "expenses", label: strings.nav.expenses, cap: "expense.view" },
  { path: "statement", label: strings.nav.statement, cap: "report.view" },
  { path: "analytics", label: strings.nav.analytics, cap: "report.view" },
  { path: "settings", label: strings.nav.settings, cap: "org.view" },
];

const ESCALATED_POLL_MS = 60_000;

/** Conversations with an open escalation, for the Inbox nav badge ("20+" past one page). */
function useEscalatedCount(orgId: string, enabled: boolean): string | undefined {
  const q = useQuery({
    queryKey: orgKey(orgId, "/conversations/", "escalated-count"),
    queryFn: ({ signal }) =>
      api<Paginated<Conversation>>(`/orgs/${orgId}/conversations/`, { query: { escalated: 1, page_size: 20 }, signal }),
    enabled,
    refetchInterval: ESCALATED_POLL_MS,
  });
  if (!q.data) return undefined;
  const n = q.data.results.length;
  if (n === 0) return undefined;
  return q.data.next ? `${n}+` : String(n);
}

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

  const [assistantOpen, setAssistantOpen] = useState(false);
  const escalated = useEscalatedCount(orgId, Boolean(ctx?.can("inbox.view")));

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

  const nav: NavItem[] = NAV.filter((n) => ctx.can(n.cap)).map((n) => ({
    to: `${ctx.base}/${n.path}`,
    label: n.label,
    ...(n.path === "inbox" && escalated ? { badge: escalated, badgeLabel: fmt(strings.nav.inboxCount, { count: escalated }) } : {}),
  }));

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
        onOpenAssistant={() => setAssistantOpen(true)}
      >
        <Outlet />
      </AppShell>
      <AssistantPanel open={assistantOpen} onClose={() => setAssistantOpen(false)} />
    </OrgContext.Provider>
  );
}
