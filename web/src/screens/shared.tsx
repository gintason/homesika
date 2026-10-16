import type { ReactNode } from "react";

import { Banner, LoadingBlock } from "../components";
import { strings } from "../i18n";
import { errorText } from "../lib/api";

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
