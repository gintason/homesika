import type { ReactNode } from "react";
import { Link } from "react-router";

export function PageHeader({
  title,
  description,
  actions,
  back,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  back?: { to: string; label: string };
}) {
  return (
    <header className="mb-6 space-y-2">
      {back && (
        <Link
          to={back.to}
          className="inline-flex min-h-touch items-center gap-1 text-base font-medium text-primary-600 underline-offset-4 hover:underline"
        >
          <span aria-hidden="true">←</span> {back.label}
        </Link>
      )}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 space-y-1">
          <h1 className="font-display text-2xl font-bold text-primary-800 md:text-3xl">{title}</h1>
          {description && <div className="text-base text-ink-600">{description}</div>}
        </div>
        {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
      </div>
    </header>
  );
}
