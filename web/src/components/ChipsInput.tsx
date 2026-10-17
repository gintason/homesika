import { useId, useState, type KeyboardEvent } from "react";

import { fmt, strings } from "../i18n";
import { Button } from "./Button";
import { cx } from "./cx";
import { inputClasses } from "./Field";

/** A list of short text items ("Prepaid meter", "Borehole") shown as removable chips. */
export function ChipsInput({
  label,
  hint,
  error,
  value,
  onChange,
  max = 30,
  maxLength = 80,
}: {
  label: string;
  hint?: string;
  error?: string | null;
  value: string[];
  onChange: (value: string[]) => void;
  max?: number;
  maxLength?: number;
}) {
  const id = useId();
  const [draft, setDraft] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const shownError = localError ?? error;

  const add = () => {
    const item = draft.trim();
    if (!item) return;
    if (item.length > maxLength) return setLocalError(strings.listings.featureTooLong);
    if (value.length >= max) return setLocalError(strings.listings.tooManyFeatures);
    if (!value.some((v) => v.toLowerCase() === item.toLowerCase())) onChange([...value, item]);
    setDraft("");
    setLocalError(null);
  };
  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      add();
    }
  };
  const describedBy = [shownError ? `${id}-error` : "", hint ? `${id}-hint` : ""].filter(Boolean).join(" ") || undefined;

  return (
    <fieldset className="space-y-2">
      <legend className="text-sm font-medium text-ink-800">
        {label} <span className="font-normal text-ink-600">({strings.common.optional})</span>
      </legend>
      {value.length > 0 && (
        <ul className="flex flex-wrap gap-2" aria-label={label}>
          {value.map((v) => (
            <li key={v} className="inline-flex items-center gap-1 rounded-pill bg-primary-50 pl-3 text-sm font-medium text-primary-800">
              {v}
              <button
                type="button"
                onClick={() => onChange(value.filter((x) => x !== v))}
                aria-label={fmt(strings.listings.removeFeature, { feature: v })}
                className="min-h-touch min-w-touch rounded-pill text-base text-primary-700 hover:bg-primary-100"
              >
                <span aria-hidden="true">×</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="flex gap-2">
        <label htmlFor={id} className="sr-only">
          {strings.listings.newFeature}
        </label>
        <input
          id={id}
          value={draft}
          onChange={(e) => {
            setDraft(e.target.value);
            setLocalError(null);
          }}
          onKeyDown={onKeyDown}
          aria-describedby={describedBy}
          aria-invalid={shownError ? true : undefined}
          className={cx(inputClasses, "flex-1")}
        />
        <Button variant="secondary" onClick={add}>
          {strings.listings.addFeature}
        </Button>
      </div>
      {hint && (
        <p id={`${id}-hint`} className="text-sm text-ink-600">
          {hint}
        </p>
      )}
      {shownError && (
        <p id={`${id}-error`} className="text-sm font-medium text-danger-700">
          {shownError}
        </p>
      )}
    </fieldset>
  );
}
