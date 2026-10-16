import type { ReactNode } from "react";

import { Logo, OfflineBanner } from "../../components";
import { strings } from "../../i18n";

export function AuthLayout({ title, intro, children }: { title: string; intro?: ReactNode; children: ReactNode }) {
  return (
    <div className="min-h-screen bg-surface-background">
      <header className="bg-primary-800 px-5 py-3">
        <div className="mx-auto max-w-md">
          <Logo inverse />
        </div>
      </header>
      <main className="mx-auto max-w-md space-y-4 px-5 py-8">
        <OfflineBanner />
        <div className="rounded-lg bg-surface-card p-6 shadow-md ring-1 ring-surface-line">
          <h1 className="font-display text-2xl font-bold text-primary-800">{title}</h1>
          {intro && <p className="mt-2 text-base text-ink-600">{intro}</p>}
          <div className="mt-6">{children}</div>
        </div>
        <p className="text-center text-sm text-ink-600">{strings.app.tagline}</p>
      </main>
    </div>
  );
}
