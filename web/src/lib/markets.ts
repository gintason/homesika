import { useQuery } from "@tanstack/react-query";

import { api } from "./api";

/** GET /markets/ (public): the countries and cities Homesika is switched on in. */
export interface Markets {
  countries: Array<{ code: string; name: string; currency: string; calling_code: string; emergency: string; bills: boolean }>;
  cities: Array<{ slug: string; name: string; state: string; country: string; areas: string[]; discos: string[] }>;
}

export function useMarkets() {
  return useQuery({
    queryKey: ["markets"],
    queryFn: ({ signal }) => api<Markets>("/markets/", { auth: false, signal }),
    staleTime: 60 * 60 * 1000,
  });
}
