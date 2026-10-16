import { create } from "zustand";

import type { Challenge } from "@/api";

/** Hand-off between the sign-up / sign-in / reset screens (in memory only). */
type AuthFlow = {
  challenge: Challenge | null;
  setupToken: string | null;
  setChallenge: (c: Challenge) => void;
  setSetupToken: (token: string) => void;
  reset: () => void;
};

export const useAuthFlow = create<AuthFlow>((set) => ({
  challenge: null,
  setupToken: null,
  setChallenge: (challenge) => set({ challenge }),
  setSetupToken: (setupToken) => set({ setupToken }),
  reset: () => set({ challenge: null, setupToken: null }),
}));
