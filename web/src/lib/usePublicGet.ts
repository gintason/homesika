import { useCallback, useEffect, useState } from "react";

import { api, ApiError, type Query } from "./api";

/**
 * GET a public (no login) endpoint without React Query, so public pages stay small. Refetches when
 * `path` or `query` change, and on retry().
 */
export function usePublicGet<T>(path: string, query?: Query) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  const queryKey = JSON.stringify(query ?? {});

  useEffect(() => {
    const ctrl = new AbortController();
    api<T>(path, { auth: false, signal: ctrl.signal, query: JSON.parse(queryKey) as Query })
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e: unknown) => {
        if (ctrl.signal.aborted) return;
        setError(e instanceof ApiError ? e : new ApiError(0, "error", String(e)));
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false);
      });
    return () => ctrl.abort();
  }, [path, queryKey, attempt]);

  const retry = useCallback(() => {
    setLoading(true);
    setAttempt((n) => n + 1);
  }, []);
  /** Refetch in the background (keeps showing the current data). */
  const reload = useCallback(() => setAttempt((n) => n + 1), []);
  return { data, error, loading, retry, reload };
}
