import { useId, type InputHTMLAttributes, type ReactNode } from "react";

import { cx } from "./cx";

export type CheckboxProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & {
  label: ReactNode;
  hint?: ReactNode;
  error?: string | null;
};

export function Checkbox({ label, hint, error, id, className, ...rest }: CheckboxProps) {
  const autoId = useId();
  const cid = id ?? autoId;
  const describedBy = [error ? `${cid}-error` : "", hint ? `${cid}-hint` : ""].filter(Boolean).join(" ") || undefined;
  return (
    <div className={cx("space-y-1", className)}>
      <label htmlFor={cid} className="flex min-h-touch cursor-pointer items-start gap-3 py-2">
        <input
          id={cid}
          type="checkbox"
          aria-describedby={describedBy}
          aria-invalid={error ? true : undefined}
          className="mt-[2px] h-5 w-5 shrink-0 accent-primary-600"
          {...rest}
        />
        <span className="text-base text-ink-800">{label}</span>
      </label>
      {hint && (
        <p id={`${cid}-hint`} className="pl-8 text-sm text-ink-600">
          {hint}
        </p>
      )}
      {error && (
        <p id={`${cid}-error`} className="pl-8 text-sm font-medium text-danger-700">
          {error}
        </p>
      )}
    </div>
  );
}

/** On/off setting. A button with role="switch" so its state is announced. */
export function Switch({
  label,
  hint,
  checked,
  onChange,
  disabled,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}) {
  const id = useId();
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <span id={`${id}-label`} className="block text-base font-medium text-ink-800">
          {label}
        </span>
        {hint && (
          <span id={`${id}-hint`} className="block text-sm text-ink-600">
            {hint}
          </span>
        )}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-labelledby={`${id}-label`}
        aria-describedby={hint ? `${id}-hint` : undefined}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className="flex min-h-touch min-w-touch shrink-0 items-center justify-center disabled:opacity-60"
      >
        <span
          aria-hidden="true"
          className={cx(
            "relative inline-block h-6 w-12 rounded-pill transition-colors duration-fast",
            checked ? "bg-primary-600" : "bg-ink-400",
          )}
        >
          <span
            className={cx(
              "absolute top-[2px] h-5 w-5 rounded-full bg-white shadow-sm transition-all duration-fast",
              checked ? "left-[26px]" : "left-[2px]",
            )}
          />
        </span>
      </button>
    </div>
  );
}
