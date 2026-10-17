import type { ReactNode } from "react";

import { Banner, LoadingBlock } from "../components";
import { strings } from "../i18n";
import { ApiError, errorText } from "../lib/api";

/** Loading / error-with-retry wrapper for a single-object page. */
export function QueryState<T>({
  data,
  isLoading,
  error,
  refetch,
  children,
}: {
  data: T | undefined;
  isLoading: boolean;
  error: unknown;
  refetch: () => unknown;
  children: (data: T) => ReactNode;
}) {
  if (isLoading) return <LoadingBlock />;
  if (error || data === undefined) {
    return (
      <Banner tone="error" title={strings.errors.loadFailed} onRetry={() => void refetch()}>
        {errorText(error)}
      </Banner>
    );
  }
  return <>{children(data)}</>;
}

/** Text link styled for tables and lists. */
export const linkClass = "font-medium text-primary-600 underline underline-offset-4 hover:text-primary-800";

/** Readable label for a payment channel / gateway code. */
export function channelLabel(code: string): string {
  const map = strings.payments.channels as Record<string, string>;
  return map[code] ?? code.replace(/_/g, " ");
}

/** One line for an action error: the first field error (e.g. publish's "status") or the summary. */
export function actionError(e: unknown): string {
  if (e instanceof ApiError) return e.formErrors[0] ?? Object.values(e.fieldErrors)[0] ?? e.message;
  return errorText(e);
}

/** Whole number from a text field: "" -> null, "3" -> 3, anything else -> NaN. */
export function parseWhole(value: string): number | null {
  const s = value.trim();
  if (!s) return null;
  return /^\d+$/.test(s) ? Number(s) : Number.NaN;
}
