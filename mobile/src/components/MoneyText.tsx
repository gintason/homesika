import { formatKobo, formatMoney } from "@/lib/money";

import { Text, type TextVariant } from "./Text";

type Props = {
  /** Decimal string from the API ("1500.00")… */
  amount?: string | null;
  /** …or integer kobo from a computed total. */
  kobo?: number;
  currency?: string;
  variant?: TextVariant;
  className?: string;
};

/** Money in Montserrat with ₦ and en-NG grouping. Screen readers get the same text. */
export function MoneyText({ amount, kobo, currency = "NGN", variant = "heading", className = "" }: Props) {
  const text = kobo !== undefined ? formatKobo(kobo, currency) : formatMoney(amount, currency);
  return (
    <Text variant={variant} className={`font-display ${className}`}>
      {text}
    </Text>
  );
}
