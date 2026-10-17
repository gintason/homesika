import { strings } from "../i18n";
import { formatMoney } from "./money";
import type { RentPeriod } from "./types";

/** "₦1,500,000.00 per year" */
export function listingPrice(l: { rent_amount: string; rent_period: RentPeriod; currency: string }): string {
  return `${formatMoney(l.rent_amount, l.currency)} ${strings.listings.periods[l.rent_period] ?? ""}`.trim();
}

/** The public listing page anyone can open: https://<this site>/l/LST-ABC123 */
export function publicListingUrl(ref: string): string {
  return `${window.location.origin}/l/${encodeURIComponent(ref)}`;
}
