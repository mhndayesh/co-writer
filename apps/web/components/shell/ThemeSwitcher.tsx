"use client";

import { useEffect, useRef, useState } from "react";
import { applyMode, getStoredMode, setStoredMode, type Mode, type Direction } from "@/lib/theme";
import { useMediaQuery } from "@/lib/useMediaQuery";

const DIRECTIONS: { value: Direction; label: string }[] = [
  { value: "ember", label: "Sienna" },
  { value: "grove", label: "Sage"   },
];

const MODES: { value: Mode; label: string }[] = [
  { value: "dark",  label: "Dark"  },
  { value: "soft",  label: "Soft"  },
  { value: "light", label: "Light" },
];

function getStoredDir(): Direction {
  if (typeof window === "undefined") return "ember";
  const v = localStorage.getItem("inkwell-dir");
  return v === "grove" ? "grove" : "ember";
}

function setStoredDir(d: Direction) {
  if (typeof window === "undefined") return;
  localStorage.setItem("inkwell-dir", d);
}

export default function ThemeSwitcher() {
  const [open,   setOpen]   = useState(false);
  const [mode,   setMode]   = useState<Mode>("soft");
  const [dir,    setDir]    = useState<Direction>("ember");
  const ref = useRef<HTMLDivElement>(null);
  // On phones, collapse the trigger to just the ink-drop swatch to save bar width.
  const compact = useMediaQuery("(max-width: 560px)");

  useEffect(() => {
    const m = getStoredMode() ?? "soft";
    const d = getStoredDir();
    setMode(m);
    setDir(d);
  }, []);

  // Close on click outside
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  function applyDir(d: Direction) {
    setDir(d);
    setStoredDir(d);
    document.documentElement.setAttribute("data-dir", d);
  }

  function applyModeChange(m: Mode) {
    setMode(m);
    setStoredMode(m);
    applyMode(m, dir);
  }

  // Dot indicator showing current active combination
  const modeLabel = MODES.find(m => m.value === mode)?.label ?? "Soft";
  const dirLabel  = DIRECTIONS.find(d => d.value === dir)?.label ?? "Sienna";

  return (
    <div ref={ref} style={{ position: "relative" }}>
      {/* Trigger button */}
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 6,
          padding: "5px 10px",
          border: open
            ? "1px solid var(--border-strong)"
            : "1px solid var(--border)",
          borderRadius: 8,
          background: open ? "var(--surface-2)" : "transparent",
          color: "var(--muted)",
          fontSize: 12,
          fontFamily: "var(--font-mono)",
          letterSpacing: "0.05em",
          cursor: "pointer",
          transition: "all 0.15s",
          whiteSpace: "nowrap",
          lineHeight: 1.4,
        }}
        onMouseEnter={e => {
          if (!open) (e.currentTarget as HTMLElement).style.background = "var(--surface-2)";
        }}
        onMouseLeave={e => {
          if (!open) (e.currentTarget as HTMLElement).style.background = "transparent";
        }}
      >
        {/* Tiny ink drop */}
        <span
          style={{
            display: "inline-block",
            width: 8, height: 8,
            background: "var(--accent)",
            borderRadius: "50% 50% 50% 2px",
            transform: "rotate(45deg)",
          }}
        />
        {!compact && (
          <>
            <span style={{ color: "var(--text)", fontWeight: 500 }}>{dirLabel}</span>
            <span style={{ color: "var(--faint)" }}>·</span>
            <span>{modeLabel}</span>
          </>
        )}
      </button>

      {/* Dropdown panel */}
      {open && (
        <div
          style={{
            position: "absolute",
            top: "calc(100% + 8px)",
            right: 0,
            width: 260,
            background: "var(--surface)",
            border: "1px solid var(--border-strong)",
            borderRadius: 14,
            boxShadow: "var(--shadow)",
            padding: "16px",
            zIndex: 100,
            display: "grid",
            gap: 20,
          }}
        >
          {/* Direction */}
          <div>
            <p
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: 10,
                letterSpacing: "0.14em",
                textTransform: "uppercase",
                color: "var(--faint)",
                marginBottom: 8,
              }}
            >
              Direction
            </p>
            <Seg
              options={DIRECTIONS}
              value={dir}
              onChange={d => applyDir(d as Direction)}
              accent={false}
            />
          </div>

          {/* Mode */}
          <div>
            <p
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: 10,
                letterSpacing: "0.14em",
                textTransform: "uppercase",
                color: "var(--faint)",
                marginBottom: 8,
              }}
            >
              Mode
            </p>
            <Seg
              options={MODES}
              value={mode}
              onChange={m => applyModeChange(m as Mode)}
              accent={true}
            />
          </div>
        </div>
      )}
    </div>
  );
}

function Seg({
  options, value, onChange, accent,
}: {
  options: { value: string; label: string }[];
  value: string;
  onChange: (v: string) => void;
  accent: boolean;
}) {
  return (
    <div
      style={{
        display: "inline-flex",
        background: "var(--surface-2)",
        border: "1px solid var(--border)",
        borderRadius: 999,
        padding: 3,
        gap: 2,
        width: "100%",
      }}
    >
      {options.map(opt => {
        const active = opt.value === value;
        return (
          <button
            key={opt.value}
            onClick={() => onChange(opt.value)}
            style={{
              flex: 1,
              appearance: "none",
              border: active ? "1px solid transparent" : "none",
              borderRadius: 999,
              padding: "7px 12px",
              cursor: "pointer",
              fontFamily: "var(--font-sans)",
              fontSize: 13.5,
              fontWeight: 600,
              transition: "all 0.18s ease",
              whiteSpace: "nowrap",
              textAlign: "center",
              lineHeight: 1.2,
              background: active
                ? accent ? "var(--accent)" : "var(--surface)"
                : "transparent",
              color: active
                ? accent ? "var(--accent-text)" : "var(--text)"
                : "var(--muted)",
              boxShadow: active && !accent ? "0 1px 2px oklch(0 0 0 / 0.18)" : "none",
            }}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
