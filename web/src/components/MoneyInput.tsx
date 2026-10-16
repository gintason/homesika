import { type InputHTMLAttributes } from "react";

import { formatPlainAmount, parseMoneyInput } from "../lib/money";
import type { FieldChrome } from "./Field";
import { TextField } from "./TextField";

export type MoneyInputProps = FieldChrome &
  Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "onChange" | "type" | "prefix"> & {
    /** What the person typed, e.g. "1,500,000". Parse with parseMoneyInput() before sending. */
    value: string;
    onChange: (value: string) => void;
    currencySymbol?: string;
  };

/** Naira amount entry. Accepts "1500000", "1,500,000.50", tidies the value on blur. */
export function MoneyInput({ value, onChange, onBlur, currencySymbol = "₦", ...rest }: MoneyInputProps) {
  return (
    <TextField
      {...rest}
      type="text"
      inputMode="decimal"
      autoComplete="off"
      prefix={currencySymbol}
      value={value}
      onChange={(e) => onChange(e.target.value.replace(/[^\d.,\s]/g, ""))}
      onBlur={(e) => {
        if (value && parseMoneyInput(value) !== null) onChange(formatPlainAmount(value));
        onBlur?.(e);
      }}
    />
  );
}
