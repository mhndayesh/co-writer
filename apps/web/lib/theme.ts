// Theme persistence. The actual class application happens in a blocking
// inline script (see ThemeBoot in app/layout.tsx) so the page paints with
// the right palette — no white flash on a dark-themed user's load.

export type Theme = "light" | "dark";

export const THEME_KEY = "gink-theme";

export function getStoredTheme(): Theme | null {
  if (typeof window === "undefined") return null;
  const v = window.localStorage.getItem(THEME_KEY);
  return v === "light" || v === "dark" ? v : null;
}

export function setStoredTheme(t: Theme) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(THEME_KEY, t);
}

export function applyTheme(t: Theme) {
  if (typeof document === "undefined") return;
  document.documentElement.classList.toggle("dark", t === "dark");
}

export function resolveInitialTheme(): Theme {
  const stored = getStoredTheme();
  if (stored) return stored;
  if (typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches) return "dark";
  return "dark"; // app's default identity is dark
}
