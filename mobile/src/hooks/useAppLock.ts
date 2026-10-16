import { useEffect, useRef } from "react";
import { AppState } from "react-native";

import { LOCK_AFTER_BACKGROUND_MS } from "@/config";
import { useSession } from "@/store/session";

/**
 * Automatic session timeout: when the app returns from the background after
 * LOCK_AFTER_BACKGROUND_MS, show the PIN screen again. Skipped while the payer is in the
 * checkout browser (otherwise the pay result screen would be lost behind the lock).
 */
export function useAppLock() {
  const lock = useSession((s) => s.lock);
  const backgroundedAt = useRef<number | null>(null);

  useEffect(() => {
    const sub = AppState.addEventListener("change", (state) => {
      if (state === "background") {
        backgroundedAt.current = Date.now();
      } else if (state === "active" && backgroundedAt.current !== null) {
        const now = Date.now();
        const suspended = useSession.getState().lockSuspendedUntil > now;
        if (!suspended && now - backgroundedAt.current >= LOCK_AFTER_BACKGROUND_MS) lock();
        backgroundedAt.current = null;
      }
    });
    return () => sub.remove();
  }, [lock]);
}
