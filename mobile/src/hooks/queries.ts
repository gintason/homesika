import { keepPreviousData, useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  allOutstandingCharges,
  artisanApi,
  authApi,
  billsApi,
  listingsApi,
  repairsApi,
  tenantApi,
  whatsappApi,
  type BillCategory,
  type ListingFilters,
} from "@/api";
import { ApiError } from "@/lib/api";

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
  tickets: ["me", "tickets"] as const,
  ticket: (id: string) => ["me", "tickets", id] as const,
  artisan: ["me", "artisan"] as const,
  jobs: (status: "active" | "history") => ["me", "jobs", status] as const,
  job: (id: string) => ["me", "job", id] as const,
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

export const useTickets = () =>
  useInfiniteQuery({
    queryKey: keys.tickets,
    queryFn: ({ pageParam }) => repairsApi.list(pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next,
  });

export const useTicket = (id: string) =>
  useQuery({ queryKey: keys.ticket(id), queryFn: () => repairsApi.get(id), enabled: Boolean(id) });

/** null = not signed up as an artisan yet (the API answers 404 not_artisan). */
export const useMyArtisan = () =>
  useQuery({
    queryKey: keys.artisan,
    queryFn: async () => {
      try {
        return await artisanApi.me();
      } catch (e) {
        if (e instanceof ApiError && e.code === "not_artisan") return null;
        throw e;
      }
    },
  });

export const useJobs = (status: "active" | "history", opts: { enabled?: boolean } = {}) =>
  useInfiniteQuery({
    queryKey: keys.jobs(status),
    queryFn: ({ pageParam }) => artisanApi.jobs(status, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next,
    enabled: opts.enabled ?? true,
  });

export const useJob = (id: string) => useQuery({ queryKey: keys.job(id), queryFn: () => artisanApi.job(id), enabled: Boolean(id) });
