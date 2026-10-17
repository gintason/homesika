import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type Query } from "./api";
import { useOrg } from "./org";
import type { Paginated } from "./types";

/** Query key for anything inside the current org; invalidate ["org", id] after a change. */
export function orgKey(orgId: string, ...parts: unknown[]) {
  return ["org", orgId, ...parts] as const;
}

/** GET a non-paginated org endpoint, e.g. useOrgQuery<Property[]>("/properties/"). */
export function useOrgQuery<T>(
  path: string,
  query?: Query,
  options: { enabled?: boolean; /** Poll every N ms (e.g. an open inbox thread). */ refetchInterval?: number } = {},
) {
  const { org } = useOrg();
  return useQuery({
    queryKey: orgKey(org.id, path, query ?? {}),
    queryFn: ({ signal }) => api<T>(`/orgs/${org.id}${path}`, { query, signal }),
    enabled: options.enabled ?? true,
    refetchInterval: options.refetchInterval,
  });
}

/** Cursor-paginated list ({next, previous, results}) with "Load more". */
export function usePaginatedList<T>(path: string, query?: Query, options: { enabled?: boolean } = {}) {
  const { org } = useOrg();
  const q = useInfiniteQuery({
    queryKey: orgKey(org.id, path, "paged", query ?? {}),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      api<Paginated<T>>(pageParam ?? `/orgs/${org.id}${path}`, { query: pageParam ? undefined : query, signal }),
    getNextPageParam: (last) => last.next ?? undefined,
    enabled: options.enabled ?? true,
  });
  return {
    rows: q.data?.pages.flatMap((p) => p.results),
    isLoading: q.isLoading,
    error: q.error,
    refetch: () => void q.refetch(),
    hasMore: Boolean(q.hasNextPage),
    loadMore: () => void q.fetchNextPage(),
    loadingMore: q.isFetchingNextPage,
  };
}

/** Fetch every page of a paginated endpoint (small lists such as one tenant's unpaid charges). */
export async function fetchAll<T>(path: string, query?: Query): Promise<T[]> {
  const out: T[] = [];
  let next: string | null = path;
  let first = true;
  while (next) {
    const page: Paginated<T> = await api<Paginated<T>>(next, { query: first ? { ...query, page_size: 100 } : undefined });
    out.push(...page.results);
    next = page.next;
    first = false;
  }
  return out;
}

export function useInvalidateOrg() {
  const { org } = useOrg();
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ["org", org.id] });
}
