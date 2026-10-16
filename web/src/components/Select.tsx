import { useId, type SelectHTMLAttributes } from "react";

import { cx } from "./cx";
import { Field, inputClasses, type FieldChrome } from "./Field";

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export type SelectProps = FieldChrome &
  SelectHTMLAttributes<HTMLSelectElement> & {
    options: ReadonlyArray<SelectOption>;
    /** Adds an empty first option, e.g. "Choose a unit". */
    placeholder?: string;
    containerClassName?: string;
  };

/** Native select: best for low-end phones and screen readers. */
export function Select({
  label,
  hint,
  error,
  optional,
  hideLabel,
  options,
  placeholder,
  id,
  className,
  containerClassName,
  ...rest
}: SelectProps) {
  const autoId = useId();
  return (
    <Field
      id={id ?? autoId}
      label={label}
      hint={hint}
      error={error}
      optional={optional}
      hideLabel={hideLabel}
      className={containerClassName}
    >
      {(a11y) => (
        <select {...a11y} {...rest} className={cx(inputClasses, "pr-8", className)}>
          {placeholder !== undefined && <option value="">{placeholder}</option>}
          {options.map((o) => (
            <option key={o.value} value={o.value} disabled={o.disabled}>
              {o.label}
            </option>
          ))}
        </select>
      )}
    </Field>
  );
}

/** Options from a {value: label} dictionary (e.g. strings.units.kinds). */
export function optionsFrom(dict: Readonly<Record<string, string>>, exclude: string[] = []): SelectOption[] {
  return Object.entries(dict)
    .filter(([v]) => !exclude.includes(v))
    .map(([value, label]) => ({ value, label }));
}
