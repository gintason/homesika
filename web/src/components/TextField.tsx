import { useId, type InputHTMLAttributes, type ReactNode, type TextareaHTMLAttributes } from "react";

import { cx } from "./cx";
import { Field, inputClasses, type FieldChrome } from "./Field";

export type TextFieldProps = FieldChrome &
  Omit<InputHTMLAttributes<HTMLInputElement>, "prefix"> & {
    /** Shown inside the field before the value, e.g. "₦". Decorative: say it in the label too. */
    prefix?: ReactNode;
    /** Shown inside the field after the value, e.g. a show/hide button. */
    suffix?: ReactNode;
    containerClassName?: string;
  };

export function TextField({
  label,
  hint,
  error,
  optional,
  hideLabel,
  prefix,
  suffix,
  id,
  className,
  containerClassName,
  ...rest
}: TextFieldProps) {
  const autoId = useId();
  const fieldId = id ?? autoId;
  return (
    <Field
      id={fieldId}
      label={label}
      hint={hint}
      error={error}
      optional={optional}
      hideLabel={hideLabel}
      className={containerClassName}
    >
      {(a11y) => (
        <div className="relative flex items-stretch">
          {prefix && (
            <span
              aria-hidden="true"
              className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-4 text-base text-ink-600"
            >
              {prefix}
            </span>
          )}
          <input
            {...a11y}
            {...rest}
            className={cx(inputClasses, prefix ? "pl-10" : undefined, suffix ? "pr-[96px]" : undefined, className)}
          />
          {suffix && <div className="absolute inset-y-0 right-0 flex items-center pr-1">{suffix}</div>}
        </div>
      )}
    </Field>
  );
}

export type TextAreaProps = FieldChrome & TextareaHTMLAttributes<HTMLTextAreaElement>;

export function TextArea({ label, hint, error, optional, hideLabel, id, className, rows = 3, ...rest }: TextAreaProps) {
  const autoId = useId();
  const fieldId = id ?? autoId;
  return (
    <Field id={fieldId} label={label} hint={hint} error={error} optional={optional} hideLabel={hideLabel}>
      {(a11y) => <textarea {...a11y} {...rest} rows={rows} className={cx(inputClasses, "py-3", className)} />}
    </Field>
  );
}
