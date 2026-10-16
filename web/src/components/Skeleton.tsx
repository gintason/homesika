import { strings } from "../i18n";
import { cx } from "./cx";

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden="true" className={cx("animate-pulse rounded-md bg-surface-muted", className ?? "h-5 w-full")} />;
}

/** Placeholder while a page or list loads; announced once as "Loading…". */
export function LoadingBlock({ rows = 4, label = strings.app.loading }: { rows?: number; label?: string }) {
  return (
    <div role="status" className="space-y-3">
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className={cx("h-12", i % 2 ? "w-4/5" : "w-full")} />
      ))}
    </div>
  );
}
