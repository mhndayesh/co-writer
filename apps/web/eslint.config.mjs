// ESLint 9 flat config. Without this file `next lint` only drops into an
// interactive setup prompt and `eslint .` errors out ("couldn't find an
// eslint.config file"), so the project had zero lint coverage.
//
// Uses FlatCompat to consume the existing eslintrc-style `eslint-config-next`
// presets (Next 15 doesn't ship a native flat config yet).
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { FlatCompat } from "@eslint/eslintrc";

const __dirname = dirname(fileURLToPath(import.meta.url));
const compat = new FlatCompat({ baseDirectory: __dirname });

export default [
  { ignores: [".next/**", "node_modules/**", "next-env.d.ts"] },
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    rules: {
      // This codebase intentionally uses `any` for the API envelope/payload
      // boundary (see lib/api.ts). Don't make it a hard lint error; real issues
      // (unused vars, hook deps, <img> LCP) still surface as warnings.
      "@typescript-eslint/no-explicit-any": "off",
      // Cosmetic JSX literal-quote escaping — high noise, not a real bug.
      "react/no-unescaped-entities": "off",
    },
  },
];
