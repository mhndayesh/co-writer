"use client";
import { useEffect, useState } from "react";
import { Sun, Moon } from "lucide-react";
import { applyTheme, getStoredTheme, setStoredTheme, type Theme } from "@/lib/theme";
import { cn } from "@/lib/cn";

export function ThemeToggle({ className }: { className?: string }) {
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    const stored = getStoredTheme();
    if (stored) setTheme(stored);
    else if (typeof document !== "undefined" && document.documentElement.classList.contains("dark")) setTheme("dark");
    else setTheme("light");
  }, []);

  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    setStoredTheme(next);
    applyTheme(next);
  }

  return (
    <button
      onClick={toggle}
      className={cn(
        "inline-flex items-center gap-1.5 px-2 py-1.5 rounded text-xs text-ink-text2 hover:text-ink-goldLight transition-colors",
        className,
      )}
      title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      aria-label="Toggle theme"
    >
      {theme === "dark" ? <Sun size={12}/> : <Moon size={12}/>}
      {theme === "dark" ? "Light mode" : "Dark mode"}
    </button>
  );
}
