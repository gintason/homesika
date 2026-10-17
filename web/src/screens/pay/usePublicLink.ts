import { usePublicGet } from "../../lib/usePublicGet";
import type { PublicLink } from "../../lib/types";

export function usePublicLink(reference: string) {
  const { data, error, loading, retry } = usePublicGet<PublicLink>(`/pay/${encodeURIComponent(reference)}/`);
  return { data, error, loading, retry };
}
