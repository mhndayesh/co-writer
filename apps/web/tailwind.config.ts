import type { Config } from "tailwindcss";

// Palette resolves to CSS variables so a single class set works for both themes.
// Dark values stay close to the original Story Forge `C` object; light values
// are a warm cream/ink complement that keeps the literary character.
const inkColor = (name: string) => `rgb(var(--ink-${name}) / <alpha-value>)`;

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        ink: {
          bg: inkColor("bg"),
          surface: inkColor("surface"),
          surface2: inkColor("surface2"),
          surface3: inkColor("surface3"),
          border: inkColor("border"),
          borderLight: inkColor("borderLight"),
          text: inkColor("text"),
          text2: inkColor("text2"),
          text3: inkColor("text3"),
          gold: inkColor("gold"),
          goldLight: inkColor("goldLight"),
          red: inkColor("red"),
          green: inkColor("green"),
          rose: inkColor("rose"),
          deep: inkColor("deep"),
        },
      },
      fontFamily: {
        display: ["Playfair Display", "Lora", "serif"],
        body: ["Lora", "Georgia", "serif"],
      },
      boxShadow: {
        ink: "0 1px 0 0 rgb(var(--ink-gold) / 0.08) inset, 0 0 0 1px rgb(var(--ink-border) / 0.6)",
      },
    },
  },
  plugins: [],
};

export default config;
