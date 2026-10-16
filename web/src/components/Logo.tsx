import { strings } from "../i18n";
import { cx } from "./cx";

export function Logo({ className, withName = true, inverse = false }: { className?: string; withName?: boolean; inverse?: boolean }) {
  return (
    <span className={cx("inline-flex items-center gap-2", className)}>
      <img src="/homesika-logo.jpg" alt={withName ? "" : strings.app.name} width={40} height={40} className="h-10 w-10 rounded-md bg-white object-cover" />
      {withName && (
        <span className={cx("font-display text-xl font-bold", inverse ? "text-white" : "text-primary-800")}>
          {strings.app.name}
        </span>
      )}
    </span>
  );
}
