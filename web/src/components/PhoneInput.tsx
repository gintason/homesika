import type { InputHTMLAttributes } from "react";

import { strings } from "../i18n";
import type { FieldChrome } from "./Field";
import { TextField } from "./TextField";

export type PhoneInputProps = Partial<FieldChrome> &
  Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "onChange" | "type" | "prefix"> & {
    value: string;
    onChange: (value: string) => void;
  };

/** Nigerian phone number: accepts 0803…, 803…, 234803… or +234 803… (normalise with normalisePhone). */
export function PhoneInput({ value, onChange, label = strings.fields.phone, hint = strings.fields.phoneHint, ...rest }: PhoneInputProps) {
  return (
    <TextField
      {...rest}
      label={label}
      hint={hint}
      type="tel"
      inputMode="tel"
      autoComplete="tel"
      value={value}
      maxLength={18}
      onChange={(e) => onChange(e.target.value.replace(/[^\d+\s-]/g, ""))}
    />
  );
}
