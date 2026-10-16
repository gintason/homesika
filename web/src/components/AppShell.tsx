import { useState, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router";

import { strings } from "../i18n";
import { OfflineBanner } from "./Banner";
import { cx } from "./cx";
import { Logo } from "./Logo";

export interface NavItem {
  to: string;
  label: string;
}

export interface OrgOption {
  id: string;
  name: string;
}

function OrgSwitcher({
  orgs,
  currentOrgId,
  onSwitch,
  id,
}: {
  orgs: OrgOption[];
  currentOrgId: string;
  /** Called with an org id, or "__new" when "Create another organization" is chosen. */
  onSwitch: (id: string) => void;
  id: string;
}) {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-xs font-semibold uppercase tracking-wide text-primary-100">
        {strings.orgs.switcher}
      </label>
      <select
        id={id}
        value={currentOrgId}
        onChange={(e) => onSwitch(e.target.value)}
        className="block min-h-touch w-full rounded-md border border-primary-600 bg-primary-700 px-3 text-base text-white"
      >
        {orgs.map((o) => (
          <option key={o.id} value={o.id}>
            {o.name}
          </option>
        ))}
        <option value="__new">+ {strings.orgs.createNew}</option>
      </select>
    </div>
  );
}

function NavList({ items, onNavigate }: { items: NavItem[]; onNavigate?: () => void }) {
  return (
    <ul className="space-y-1">
      {items.map((item) => (
        <li key={item.to}>
          <NavLink
            to={item.to}
            onClick={onNavigate}
            className={({ isActive }) =>
              cx(
                "flex min-h-touch items-center rounded-md border-l-4 px-3 text-base font-medium",
                isActive
                  ? "border-gold-400 bg-primary-700 text-white"
                  : "border-transparent text-primary-50 hover:bg-primary-700 hover:text-white",
              )
            }
          >
            {item.label}
          </NavLink>
        </li>
      ))}
    </ul>
  );
}

/**
 * Staff layout. Wide screens: navy sidebar with org switcher and nav. Phones: navy top bar with a
 * Menu button that opens the same navigation as a full-height panel.
 */
export function AppShell({
  nav,
  orgs,
  currentOrgId,
  onSwitchOrg,
  createOrgHref,
  userName,
  onSignOut,
  children,
}: {
  nav: NavItem[];
  orgs: OrgOption[];
  currentOrgId: string;
  /** Called with the chosen org id, or with createOrgHref when "create another" is chosen. */
  onSwitchOrg: (idOrHref: string) => void;
  createOrgHref: string;
  userName: string;
  onSignOut: () => void;
  children: ReactNode;
}) {
  const location = useLocation();
  // The menu belongs to the page it was opened on, so it closes by itself after any navigation.
  const [menuPath, setMenuPath] = useState<string | null>(null);
  const menuOpen = menuPath === location.pathname;
  const setMenuOpen = (open: boolean) => setMenuPath(open ? location.pathname : null);

  const sidebar = (idSuffix: string, onNavigate?: () => void) => (
    <div className="flex h-full flex-col gap-6 p-4">
      <OrgSwitcher
        id={`org-switcher-${idSuffix}`}
        orgs={orgs}
        currentOrgId={currentOrgId}
        onSwitch={(id) => onSwitchOrg(id === "__new" ? createOrgHref : id)}
      />
      <nav aria-label={strings.nav.main}>
        <NavList items={nav} onNavigate={onNavigate} />
      </nav>
      <div className="mt-auto space-y-2 border-t border-primary-700 pt-4">
        <p className="truncate px-3 text-sm text-primary-100">{userName}</p>
        <button
          type="button"
          onClick={onSignOut}
          className="flex min-h-touch w-full items-center rounded-md px-3 text-base font-medium text-primary-50 hover:bg-primary-700"
        >
          {strings.auth.signOut}
        </button>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-surface-background lg:flex">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-white focus:px-4 focus:py-3"
      >
        {strings.app.skipToContent}
      </a>

      {/* Desktop sidebar */}
      <aside className="hidden w-[272px] shrink-0 bg-primary-800 lg:block">
        <div className="sticky top-0 flex h-screen flex-col">
          <div className="px-4 pt-5">
            <Logo inverse />
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">{sidebar("desktop")}</div>
        </div>
      </aside>

      {/* Mobile top bar */}
      <header className="sticky top-0 z-30 flex items-center justify-between bg-primary-800 px-4 py-2 lg:hidden">
        <Logo inverse />
        <button
          type="button"
          aria-expanded={menuOpen}
          aria-controls="mobile-menu"
          onClick={() => setMenuOpen(!menuOpen)}
          className="min-h-touch min-w-touch rounded-md px-3 text-base font-semibold text-white hover:bg-primary-700"
        >
          {menuOpen ? strings.nav.closeMenu : strings.nav.menu}
        </button>
      </header>
      {menuOpen && (
        <div id="mobile-menu" className="fixed inset-x-0 bottom-0 top-[64px] z-30 overflow-y-auto bg-primary-800 lg:hidden">
          {sidebar("mobile", () => setMenuOpen(false))}
        </div>
      )}

      <div className="min-w-0 flex-1">
        <div className="mx-auto max-w-[1120px] space-y-4 px-5 py-6 md:px-8 md:py-8">
          <OfflineBanner />
          <main id="main" tabIndex={-1} className="focus:outline-none">
            {children}
          </main>
        </div>
      </div>
    </div>
  );
}
