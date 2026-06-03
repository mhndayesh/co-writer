import { create } from "zustand";

export type ViewMode = "flow" | "studio" | "voice";

// Why the upgrade modal opened — drives its headline copy.
export type UpgradeReason = "subscription_required" | "quota_exceeded" | "byok_key_missing" | "manual";

interface UIState {
  viewMode: ViewMode;
  setViewMode: (m: ViewMode) => void;
  llmReachable: boolean | null;
  setLlmReachable: (r: boolean | null) => void;

  // Upgrade / paywall modal (opened from anywhere — including non-React code).
  upgradeOpen: boolean;
  upgradeReason: UpgradeReason;
  openUpgrade: (reason?: UpgradeReason) => void;
  closeUpgrade: () => void;
}

export const useUI = create<UIState>((set) => ({
  viewMode: "flow",
  setViewMode: (m) => set({ viewMode: m }),
  llmReachable: null,
  setLlmReachable: (r) => set({ llmReachable: r }),

  upgradeOpen: false,
  upgradeReason: "manual",
  openUpgrade: (reason = "manual") => set({ upgradeOpen: true, upgradeReason: reason }),
  closeUpgrade: () => set({ upgradeOpen: false }),
}));
