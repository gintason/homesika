import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";

import { allOutstandingCharges, authApi, tenantApi } from "@/api";

/** Everything here is per-user; the root layout clears the cache on sign-out. */
export const keys = {
  me: ["me"] as const,
  leases: ["me", "leases"] as const,
  charges: ["me", "charges"] as const,
  charge: (id: string) => ["me", "charge", id] as const,
  payments: ["me", "payments"] as const,
};

export const useMe = () => useQuery({ queryKey: keys.me, queryFn: authApi.me });
export const useLeases = () => useQuery({ queryKey: keys.leases, queryFn: tenantApi.leases });
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
