import type { NextConfig } from "next";
import { join } from "node:path";

const config: NextConfig = {
  outputFileTracingRoot: join(process.cwd(), "../.."),
  reactStrictMode: true,
  output: "standalone",
  assetPrefix: process.env.NEXT_PUBLIC_CDN_URL || "",
  // Lint via the dedicated `npm run lint` (eslint.config.mjs); don't gate the
  // production build on it so a style warning can't break a deploy.
  eslint: { ignoreDuringBuilds: true },

  // Baseline security headers (defense in depth). A strict Content-Security-Policy
  // is intentionally omitted here — Clerk + Next inject inline/eval scripts, so a
  // CSP needs per-deployment nonces/allowlisting and dedicated testing before it
  // can ship without breaking auth. The headers below are safe everywhere.
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
};

export default config;
