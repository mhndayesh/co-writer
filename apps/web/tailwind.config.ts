import type { Config } from "tailwindcss";

const iw = (name: string) => `rgb(var(--iw-${name}) / <alpha-value>)`;
const ink = (name: string) => `rgb(var(--ink-${name}) / <alpha-value>)`;

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // New G-Ink Studio semantic tokens
        iw: {
          bg:          iw("bg"),
          surface:     iw("surface"),
          "surface-2": iw("surface-2"),
          text:        iw("text"),
          muted:       iw("muted"),
          faint:       iw("faint"),
          border:      iw("border"),
          "border-s":  iw("border-s"),
          accent:      iw("accent"),
          "accent-2":  iw("accent-2"),
          "accent-t":  iw("accent-text"),
          "accent-s":  iw("accent-soft"),
        },
        // Legacy ink-* tokens (backward compat with studio pages)
        ink: {
          bg:          ink("bg"),
          surface:     ink("surface"),
          surface2:    ink("surface2"),
          surface3:    ink("surface3"),
          border:      ink("border"),
          borderLight: ink("borderLight"),
          text:        ink("text"),
          text2:       ink("text2"),
          text3:       ink("text3"),
          gold:        ink("gold"),
          goldLight:   ink("goldLight"),
          red:         ink("red"),
          green:       ink("green"),
          rose:        ink("rose"),
          deep:        ink("deep"),
        },
      },
      fontFamily: {
        // New G-Ink Studio fonts
        serif:   ["Newsreader", "Georgia", "serif"],
        sans:    ["Hanken Grotesk", "system-ui", "sans-serif"],
        mono:    ["IBM Plex Mono", "ui-monospace", "monospace"],
        // Legacy (studio uses these)
        display: ["Newsreader", "Georgia", "serif"],
        body:    ["Newsreader", "Georgia", "serif"],
      },
      borderRadius: {
        "iw-sm": "6px",
        "iw-md": "10px",
        "iw-lg": "16px",
        "iw-xl": "22px",
      },
      boxShadow: {
        iw:  "var(--shadow)",
        ink: "0 1px 0 0 rgb(var(--ink-gold) / 0.08) inset, 0 0 0 1px rgb(var(--ink-border) / 0.6)",
      },
    },
  },
  plugins: [],
};

export default config;
