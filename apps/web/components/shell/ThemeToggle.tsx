"use client";
import { useEffect, useState } from "react";
import { Sun, Moon, Sunset } from "lucide-react";
import { applyMode, getStoredMode, setStoredMode, nextMode, type Mode, type Direction } from "@/lib/theme";
import { cn } from "@/lib/cn";

const ICONS: Record<Mode, React.ReactNode> = {
  soft:  <Sunset  size={12} />,
  dark:  <Moon    size={12} />,
  light: <Sun     size={12} />,
};

const LABELS: Record<Mode, string> = {
  soft:  "Soft",
  dark:  "Dark",
  light: "Light",
};

export function ThemeToggle({ className }: { className?: string }) {
  const [mode, setMode] = useState<Mode>("soft");

  useEffect(() => {
    const stored = getStoredMode();
    const html = document.documentElement;
    const attr = html.getAttribute("data-mode") as Mode | null;
    setMode(stored ?? attr ?? "soft");
  }, []);

  function cycle() {
    const next = nextMode(mode);
    setMode(next);
    setStoredMode(next);
    // Preserve the active color direction instead of resetting it to "ember".
    const dir = (document.documentElement.getAttribute("data-dir") as Direction | null) ?? "ember";
    applyMode(next, dir);
  }

  return (
    <button
      onClick={cycle}
      className={cn(
        "inline-flex items-center gap-1.5 px-2 py-1.5 rounded-lg text-xs transition-colors",
        "text-iw-muted hover:text-iw-text border border-transparent hover:border-iw-border",
        className,
      )}
      title={`Switch to ${nextMode(mode)} mode`}
      aria-label="Toggle theme"
    >
      {ICONS[mode]}
      <span className="hidden sm:inline font-mono tracking-wider uppercase text-[10px]">{LABELS[mode]}</span>
    </button>
  );
}
