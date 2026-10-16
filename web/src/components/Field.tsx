import type { ReactNode } from "react";

import { strings } from "../i18n";
import { cx } from "./cx";

export const inputClasses = cx(
  "block w-full min-h-touch rounded-md border border-ink-400 bg-surface-card px-4 py-2 text-base text-ink-800",
  "placeholder:text-ink-500 disabled:bg-surface-muted disabled:text-ink-600",
  "aria-[invalid=true]:border-danger-500 aria-[invalid=true]:border-2",
);

export interface FieldChrome {
  label: ReactNode;
  hint?: ReactNode;
  error?: string | null;
  optional?: boolean;
  /** Visually hide the label (it stays available to screen readers). */
  hideLabel?: boolean;
}

/** Label + hint + error around a control. The control gets id, aria-describedby and aria-invalid. */
export function Field({
  id,
  label,
  hint,
  error,
  optional,
  hideLabel,
  className,
  children,
}: FieldChrome & {
  id: string;
  className?: string;
  children: (a11y: { id: string; "aria-describedby"?: string; "aria-invalid"?: boolean }) => ReactNode;
}) {
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [errorId, hintId].filter(Boolean).join(" ") || undefined;
  return (
    <div className={cx("space-y-1", className)}>
      <label htmlFor={id} className={cx("block text-sm font-medium text-ink-800", hideLabel && "sr-only")}>
        {label}
        {optional && <span className="font-normal text-ink-600"> ({strings.common.optional})</span>}
      </label>
      {children({ id, "aria-describedby": describedBy, "aria-invalid": error ? true : undefined })}
      {hint && (
        <p id={hintId} className="text-sm text-ink-600">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className="text-sm font-medium text-danger-700">
          {error}
        </p>
      )}
    </div>
  );
}
