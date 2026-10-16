import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "./api";

export function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        gcTime: 24 * 60 * 60 * 1000, // keep last-loaded data to show while offline
        // Don't hammer the API on 4xx (validation, auth); retry transient failures with backoff.
        retry: (count, error) => !(error instanceof ApiError && error.status >= 400 && error.status < 500) && count < 2,
        retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000),
      },
      mutations: { retry: false }, // money actions are retried only by the user, with the same idempotency key
    },
  });
}
