import { useState, type InputHTMLAttributes } from "react";

import { strings } from "../i18n";
import type { FieldChrome } from "./Field";
import { TextField } from "./TextField";

export type PinInputProps = FieldChrome &
  Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "onChange" | "type"> & {
    value: string;
    onChange: (value: string) => void;
    length?: 4 | 6;
    /** "current" when signing in, "new" when choosing a PIN (affects password-manager behaviour). */
    mode?: "current" | "new";
  };

/** Digits-only secret entry with a show/hide toggle. Numeric keypad on phones. */
export function PinInput({ value, onChange, length = 6, mode = "current", ...rest }: PinInputProps) {
  const [visible, setVisible] = useState(false);
  return (
    <TextField
      {...rest}
      type={visible ? "text" : "password"}
      inputMode="numeric"
      pattern="[0-9]*"
      autoComplete={mode === "new" ? "new-password" : "current-password"}
      maxLength={length}
      value={value}
      className="font-mono text-xl tracking-[0.4em]"
      onChange={(e) => onChange(e.target.value.replace(/\D/g, "").slice(0, length))}
      suffix={
        <button
          type="button"
          className="min-h-touch rounded-md px-3 text-sm font-semibold text-primary-600 hover:bg-primary-50"
          // A toggle keeps one name; aria-pressed says whether the PIN is currently shown.
          aria-label={`${strings.common.show} PIN`}
          aria-pressed={visible}
          onClick={() => setVisible((v) => !v)}
        >
          {visible ? strings.common.hide : strings.common.show}
        </button>
      }
    />
  );
}
