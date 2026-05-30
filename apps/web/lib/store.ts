import { create } from "zustand";

export type ViewMode = "flow" | "studio";

interface UIState {
  viewMode: ViewMode;
  setViewMode: (m: ViewMode) => void;
  llmReachable: boolean | null;
  setLlmReachable: (r: boolean | null) => void;
}

export const useUI = create<UIState>((set) => ({
  viewMode: "flow",
  setViewMode: (m) => set({ viewMode: m }),
  llmReachable: null,
  setLlmReachable: (r) => set({ llmReachable: r }),
}));
