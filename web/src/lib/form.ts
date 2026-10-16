import { useCallback, useState, type ChangeEvent } from "react";

import { ApiError, errorText } from "./api";

/**
 * Small form state helper: values, per-field errors, and a form-level error. API validation errors map
 * onto fields; errors for fields this form doesn't show are added to the form-level message.
 */
export function useForm<T extends Record<string, unknown>>(initial: T) {
  const [values, setValues] = useState<T>(initial);
  const [errors, setErrors] = useState<Record<string, string | undefined>>({});
  const [formError, setFormError] = useState<string | null>(null);

  const set = useCallback(<K extends keyof T>(key: K, value: T[K]) => {
    setValues((v) => ({ ...v, [key]: value }));
    setErrors((e) => (e[key as string] ? { ...e, [key as string]: undefined } : e));
  }, []);

  /** Props for a text-like input bound to `key`. */
  const text = (key: keyof T & string) => ({
    name: key,
    value: String(values[key] ?? ""),
    onChange: (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
      set(key, e.target.value as T[typeof key]),
    error: errors[key],
  });

  const fromApiError = (e: unknown) => {
    if (e instanceof ApiError) {
      const known: Record<string, string> = {};
      const unknown: string[] = [];
      for (const [k, msg] of Object.entries(e.fieldErrors)) {
        if (k in values) known[k] = msg;
        else unknown.push(msg);
      }
      setErrors(known);
      const parts = [...e.formErrors, ...unknown];
      setFormError(parts.length ? parts.join(" ") : Object.keys(known).length ? e.message : e.summary);
    } else {
      setFormError(errorText(e));
    }
  };

  /** Set client-side errors; returns true when there are none. */
  const validate = (found: Record<string, string | undefined>) => {
    const clean = Object.fromEntries(Object.entries(found).filter(([, v]) => v));
    setErrors(clean);
    setFormError(null);
    return Object.keys(clean).length === 0;
  };

  return { values, setValues, set, text, errors, setErrors, formError, setFormError, fromApiError, validate };
}
