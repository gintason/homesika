import type { InputHTMLAttributes } from "react";

import { strings } from "../i18n";
import type { FieldChrome } from "./Field";
import { TextField } from "./TextField";

export type OtpInputProps = Partial<FieldChrome> &
  Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "onChange" | "type"> & {
    value: string;
    onChange: (value: string) => void;
    length?: number;
  };

/**
 * One-time code. A single field (not one box per digit) so SMS autofill, paste and screen readers all
 * work; autocomplete="one-time-code" lets Android/iOS offer the code from the message.
 */
export function OtpInput({ value, onChange, length = 6, label = strings.auth.otpLabel, ...rest }: OtpInputProps) {
  return (
    <TextField
      {...rest}
      label={label}
      type="text"
      inputMode="numeric"
      autoComplete="one-time-code"
      pattern="[0-9]*"
      maxLength={length}
      value={value}
      className="font-mono text-2xl tracking-[0.5em]"
      onChange={(e) => onChange(e.target.value.replace(/\D/g, "").slice(0, length))}
    />
  );
}
