import type { NextConfig } from "next";
import { join } from "node:path";

const config: NextConfig = {
  outputFileTracingRoot: join(process.cwd(), "../.."),
  reactStrictMode: true,
};

export default config;
