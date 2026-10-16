import { useEffect, useState, type ReactNode } from "react";

import { strings } from "../i18n";
import { Button } from "./Button";
import { cx } from "./cx";

export type BannerTone = "error" | "offline" | "info" | "success" | "warning";

const TONES: Record<BannerTone, string> = {
  error: "border-danger-500 bg-danger-50 text-danger-700",
  offline: "border-ink-500 bg-surface-muted text-ink-800",
  info: "border-primary-500 bg-primary-50 text-primary-800",
  success: "border-success-500 bg-success-50 text-success-700",
  warning: "border-warning-500 bg-warning-50 text-warning-700",
};

export function Banner({
  tone = "info",
  title,
  children,
  onRetry,
  retryLabel = strings.common.retry,
  className,
}: {
  tone?: BannerTone;
  title?: ReactNode;
  children?: ReactNode;
  onRetry?: () => void;
  retryLabel?: string;
  className?: string;
}) {
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={cx("flex flex-wrap items-center gap-3 rounded-md border-l-4 px-4 py-3", TONES[tone], className)}
    >
      <div className="min-w-0 flex-1">
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className="text-sm">{children}</div>}
      </div>
      {onRetry && (
        <Button variant="secondary" onClick={onRetry}>
          {retryLabel}
        </Button>
      )}
    </div>
  );
}

export function useOnline(): boolean {
  const [online, setOnline] = useState(() => (typeof navigator === "undefined" ? true : navigator.onLine));
  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, []);
  return online;
}

export function OfflineBanner() {
  const online = useOnline();
  if (online) return null;
  return <Banner tone="offline">{strings.errors.offline}</Banner>;
}
