import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { strings } from "../i18n";
import { Banner } from "./Banner";
import { Button } from "./Button";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Modal dialog: traps focus, closes on Escape, returns focus to what opened it. variant="drawer" is
 * the same dialog as a full-height panel sliding in from the right (detail drawers, the assistant).
 */
export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  variant = "modal",
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  variant?: "modal" | "drawer";
}) {
  const titleId = useId();
  const descId = useId();
  const panel = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  });

  useEffect(() => {
    if (!open) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const node = panel.current;
    const first = node?.querySelector<HTMLElement>(FOCUSABLE);
    (first ?? node)?.focus();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onCloseRef.current();
      } else if (e.key === "Tab" && node) {
        const items = Array.from(node.querySelectorAll<HTMLElement>(FOCUSABLE));
        if (items.length === 0) return;
        const firstEl = items[0];
        const lastEl = items[items.length - 1];
        if (e.shiftKey && document.activeElement === firstEl) {
          e.preventDefault();
          lastEl?.focus();
        } else if (!e.shiftKey && document.activeElement === lastEl) {
          e.preventDefault();
          firstEl?.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
      previouslyFocused?.focus?.();
    };
  }, [open]);

  if (!open) return null;
  const drawer = variant === "drawer";
  return createPortal(
    <div
      className={
        drawer
          ? "fixed inset-0 z-40 flex justify-end bg-surface-overlay"
          : "fixed inset-0 z-40 flex items-end justify-center bg-surface-overlay p-0 sm:items-center sm:p-4"
      }
    >
      <div className="absolute inset-0" aria-hidden="true" onClick={onClose} />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descId : undefined}
        tabIndex={-1}
        className={
          drawer
            ? "relative flex h-full w-full max-w-lg flex-col overflow-y-auto bg-surface-card p-5 shadow-lg md:p-6"
            : "relative max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-t-xl bg-surface-card p-6 shadow-lg sm:rounded-xl"
        }
      >
        <div className="flex items-start justify-between gap-3">
          <h2 id={titleId} className="font-display text-xl font-semibold text-ink-900">
            {title}
          </h2>
          {drawer && (
            <Button variant="ghost" onClick={onClose} className="-mr-2 -mt-2 shrink-0">
              {strings.common.close}
            </Button>
          )}
        </div>
        {description && (
          <div id={descId} className="mt-2 text-base text-ink-600">
            {description}
          </div>
        )}
        {children && <div className="mt-4 space-y-4">{children}</div>}
        {footer && (
          <div
            className={
              drawer
                ? "sticky bottom-0 -mx-5 mt-auto bg-surface-card px-5 pt-4 md:-mx-6 md:px-6"
                : "mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end"
            }
          >
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}

/** "Are you sure?" with an optional form body (e.g. a reason). */
export function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  description,
  confirmLabel,
  destructive = false,
  loading = false,
  error,
  children,
  confirmDisabled,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  description?: ReactNode;
  confirmLabel: string;
  destructive?: boolean;
  loading?: boolean;
  error?: string | null;
  children?: ReactNode;
  confirmDisabled?: boolean;
}) {
  return (
    <Dialog
      open={open}
      onClose={loading ? () => undefined : onClose}
      title={title}
      description={description}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={loading}>
            {strings.common.cancel}
          </Button>
          <Button
            variant={destructive ? "destructive" : "primary"}
            onClick={onConfirm}
            loading={loading}
            disabled={confirmDisabled}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      {error && <Banner tone="error">{error}</Banner>}
      {children}
    </Dialog>
  );
}
