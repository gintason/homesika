import { useEffect, useRef, useState } from "react";

import { strings } from "../i18n";
import { Button, type ButtonVariant } from "./Button";

/** Copies `text` to the clipboard and says "Copied" for a moment (announced to screen readers). */
export function CopyButton({
  text,
  label,
  variant = "secondary",
  ariaLabel,
}: {
  text: string;
  label: string;
  variant?: ButtonVariant;
  ariaLabel?: string;
}) {
  const [copied, setCopied] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => setCopied(false), 2500);
    } catch {
      /* clipboard blocked: the text is visible and selectable */
    }
  };
  return (
    <>
      <Button variant={variant} onClick={() => void copy()} aria-label={ariaLabel}>
        {copied ? strings.common.copied : label}
      </Button>
      <span aria-live="polite" className="sr-only">
        {copied ? strings.common.copied : ""}
      </span>
    </>
  );
}
