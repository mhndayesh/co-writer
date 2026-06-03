export type Mode = "dark" | "soft" | "light";
export type Direction = "ember" | "grove";

export const THEME_KEY = "inkwell-theme";

export function getStoredMode(): Mode | null {
  if (typeof window === "undefined") return null;
  const v = window.localStorage.getItem(THEME_KEY);
  return v === "dark" || v === "soft" || v === "light" ? v as Mode : null;
}

export function setStoredMode(m: Mode) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(THEME_KEY, m);
}

export function applyMode(m: Mode, dir: Direction = "ember") {
  if (typeof document === "undefined") return;
  const html = document.documentElement;
  html.setAttribute("data-mode", m);
  html.setAttribute("data-dir", dir);
  // Keep .dark class in sync for backward compat with studio pages
  html.classList.toggle("dark", m === "dark");
}

export function nextMode(current: Mode): Mode {
  const cycle: Mode[] = ["soft", "dark", "light"];
  return cycle[(cycle.indexOf(current) + 1) % cycle.length];
}

export function resolveInitialMode(): Mode {
  const stored = getStoredMode();
  if (stored) return stored;
  // Default: soft (warm paper, easy on the eyes)
  return "soft";
}

// Legacy compat — old code called these
export type Theme = Mode;
export const getStoredTheme = getStoredMode;
export const setStoredTheme = setStoredMode;
export function applyTheme(t: Mode) { applyMode(t); }
