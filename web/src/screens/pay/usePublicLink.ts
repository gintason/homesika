import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "../../lib/api";
import type { PublicLink } from "../../lib/types";

export function usePublicLink(reference: string) {
  const [data, setData] = useState<PublicLink | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const ctrl = new AbortController();
    api<PublicLink>(`/pay/${encodeURIComponent(reference)}/`, { auth: false, signal: ctrl.signal })
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
  }, [reference, attempt]);

  const retry = useCallback(() => {
    setLoading(true);
    setAttempt((n) => n + 1);
  }, []);
  return { data, error, loading, retry };
}
