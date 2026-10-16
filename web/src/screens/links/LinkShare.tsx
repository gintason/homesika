import { useState } from "react";

import { Button, TextField } from "../../components";
import { fmt, strings } from "../../i18n";

const t = strings.links;

/** Shows the pay URL with Copy and (where the phone supports it) Share. */
export function LinkShare({ url, compact = false }: { url: string; compact?: boolean }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2500);
    } catch {
      /* clipboard blocked: the URL is visible and selectable */
    }
  };
  const canShare = typeof navigator !== "undefined" && typeof navigator.share === "function";
  return (
    <div className="space-y-2">
      {!compact && <TextField label={t.url} value={url} readOnly onFocus={(e) => e.currentTarget.select()} />}
      <div className="flex flex-wrap gap-2">
        <Button variant={compact ? "ghost" : "secondary"} onClick={() => void copy()} aria-label={compact ? `${t.copyLink}: ${url}` : undefined}>
          {copied ? strings.common.copied : t.copyLink}
        </Button>
        {canShare && (
          <Button
            variant={compact ? "ghost" : "secondary"}
            onClick={() => void navigator.share({ text: fmt(t.shareText, { url }), url }).catch(() => undefined)}
          >
            {t.shareLink}
          </Button>
        )}
      </div>
      <span aria-live="polite" className="sr-only">
        {copied ? strings.common.copied : ""}
      </span>
    </div>
  );
}
