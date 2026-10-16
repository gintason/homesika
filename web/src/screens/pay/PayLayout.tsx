import type { ReactNode } from "react";

import { Logo, OfflineBanner } from "../../components";
import { strings } from "../../i18n";

/** Lightweight public layout for SMS/WhatsApp pay links (no dashboard code, no React Query). */
export function PayLayout({ children, title }: { children: ReactNode; title: string }) {
  return (
    <div className="min-h-screen bg-surface-background">
      <header className="bg-primary-800 px-5 py-3">
        <div className="mx-auto max-w-md">
          <Logo inverse />
        </div>
      </header>
      <main className="mx-auto max-w-md space-y-4 px-5 py-6">
        <OfflineBanner />
        <h1 className="font-display text-2xl font-bold text-primary-800">{title}</h1>
        {children}
        <p className="pt-4 text-center text-sm text-ink-600">{strings.pay.poweredBy}</p>
      </main>
    </div>
  );
}

export function receiptPdfUrl(apiUrl: string, reference: string): string {
  return `${apiUrl}/api/v1/pay/${encodeURIComponent(reference)}/receipt/`;
}
