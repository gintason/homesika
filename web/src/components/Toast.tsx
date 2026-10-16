import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";

import { strings } from "../i18n";
import { cx } from "./cx";

type ToastTone = "success" | "error" | "info";
interface ToastItem {
  id: number;
  message: string;
  tone: ToastTone;
}

interface ToastApi {
  show: (message: string, tone?: ToastTone) => void;
}

const ToastContext = createContext<ToastApi>({ show: () => undefined });

export function useToast(): ToastApi {
  return useContext(ToastContext);
}

/** Short confirmations ("Payment recorded"). Announced politely; errors that need action use Banner. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const nextId = useRef(1);
  const dismiss = useCallback((id: number) => setItems((all) => all.filter((t) => t.id !== id)), []);
  const show = useCallback(
    (message: string, tone: ToastTone = "success") => {
      const id = nextId.current++;
      setItems((all) => [...all.slice(-2), { id, message, tone }]);
      window.setTimeout(() => dismiss(id), 5000);
    },
    [dismiss],
  );
  const api = useMemo(() => ({ show }), [show]);
  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        aria-live="polite"
        role="region"
        aria-label="Notifications"
        className="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex flex-col items-center gap-2 p-4"
      >
        {items.map((t) => (
          <div
            key={t.id}
            className={cx(
              "pointer-events-auto flex w-full max-w-md items-center gap-3 rounded-md px-4 py-3 text-white shadow-lg",
              t.tone === "error" ? "bg-danger-700" : t.tone === "info" ? "bg-primary-800" : "bg-success-700",
            )}
          >
            <p className="flex-1 text-base">{t.message}</p>
            <button
              type="button"
              className="min-h-touch min-w-touch rounded-md text-sm font-semibold underline"
              onClick={() => dismiss(t.id)}
            >
              {strings.common.close}
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
