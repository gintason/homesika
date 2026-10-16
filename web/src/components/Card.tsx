import type { HTMLAttributes, ReactNode } from "react";

import { cx } from "./cx";

export function Card({
  title,
  actions,
  children,
  className,
  as: As = "section",
  ...rest
}: HTMLAttributes<HTMLElement> & { title?: ReactNode; actions?: ReactNode; as?: "section" | "div" | "article" }) {
  return (
    <As className={cx("rounded-lg bg-surface-card p-5 shadow-sm ring-1 ring-surface-line md:p-6", className)} {...rest}>
      {(title || actions) && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          {title && <h2 className="font-display text-lg font-semibold text-ink-900">{title}</h2>}
          {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
        </div>
      )}
      {children}
    </As>
  );
}

/** A key number, e.g. "Overdue rent: ₦450,000". */
export function StatCard({
  label,
  value,
  detail,
  tone = "default",
  children,
}: {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  tone?: "default" | "danger" | "success";
  children?: ReactNode;
}) {
  return (
    <div className="rounded-lg bg-surface-card p-5 shadow-sm ring-1 ring-surface-line">
      <p className="text-sm font-medium text-ink-600">{label}</p>
      <p
        className={cx(
          "mt-1 font-display text-2xl font-bold",
          tone === "danger" ? "text-danger-700" : tone === "success" ? "text-success-700" : "text-ink-900",
        )}
      >
        {value}
      </p>
      {detail && <p className="mt-1 text-sm text-ink-600">{detail}</p>}
      {children}
    </div>
  );
}

/** Label/value pairs (details of a lease, payment, tenant...). */
export function DescriptionList({ items }: { items: Array<{ label: string; value: ReactNode } | false | null> }) {
  return (
    <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
      {items.filter(Boolean).map((item) => {
        const { label, value } = item as { label: string; value: ReactNode };
        return (
          <div key={label}>
            <dt className="text-sm text-ink-600">{label}</dt>
            <dd className="mt-1 break-words text-base text-ink-800">{value === "" || value == null ? "—" : value}</dd>
          </div>
        );
      })}
    </dl>
  );
}
