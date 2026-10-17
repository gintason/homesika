import { keepPreviousData, useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";

import { allOutstandingCharges, authApi, billsApi, listingsApi, tenantApi, whatsappApi, type BillCategory, type ListingFilters } from "@/api";

/** Everything here is per-user; the root layout clears the cache on sign-out. */
export const keys = {
  me: ["me"] as const,
  leases: ["me", "leases"] as const,
  charges: ["me", "charges"] as const,
  charge: (id: string) => ["me", "charge", id] as const,
  payments: ["me", "payments"] as const,
  assistant: ["me", "assistant"] as const,
  whatsapp: ["me", "whatsapp"] as const,
  listings: (f: ListingFilters) => ["listings", f] as const,
  listing: (ref: string) => ["listing", ref] as const,
  billsCatalogue: (category: BillCategory) => ["bills", "catalogue", category] as const,
  billOrders: ["me", "bills", "orders"] as const,
};

export const useMe = () => useQuery({ queryKey: keys.me, queryFn: authApi.me });
export const useLeases = (opts: { enabled?: boolean } = {}) =>
  useQuery({ queryKey: keys.leases, queryFn: tenantApi.leases, enabled: opts.enabled ?? true });
export const useOutstandingCharges = () => useQuery({ queryKey: keys.charges, queryFn: allOutstandingCharges });
export const useCharge = (id: string) =>
  useQuery({ queryKey: keys.charge(id), queryFn: () => tenantApi.charge(id), enabled: Boolean(id) });

export const usePayments = () =>
  useInfiniteQuery({
    queryKey: keys.payments,
    queryFn: ({ pageParam }) => tenantApi.payments(pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next,
  });

/** After a payment: charges, balances and payments all change. */
export function useInvalidateMoney() {
  const qc = useQueryClient();
  return () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: keys.charges }),
      qc.invalidateQueries({ queryKey: keys.payments }),
      qc.invalidateQueries({ queryKey: ["me", "charge"] }),
    ]);
}

export const useWhatsApp = () => useQuery({ queryKey: keys.whatsapp, queryFn: whatsappApi.get });
export const useListings = (f: ListingFilters) => useQuery({ queryKey: keys.listings(f), queryFn: () => listingsApi.search(f), placeholderData: keepPreviousData });
export const useListing = (ref: string) =>
  useQuery({ queryKey: keys.listing(ref), queryFn: () => listingsApi.detail(ref), enabled: Boolean(ref) });

/** Public catalogue; changes rarely (plans are synced from the provider), so keep it a while. */
export const useBillsCatalogue = (category: BillCategory) =>
  useQuery({ queryKey: keys.billsCatalogue(category), queryFn: () => billsApi.catalogue(category), staleTime: 10 * 60 * 1000 });

export const useBillOrders = () =>
  useInfiniteQuery({
    queryKey: keys.billOrders,
    queryFn: ({ pageParam }) => billsApi.orders(pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next,
  });
