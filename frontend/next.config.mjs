import { fileURLToPath } from "node:url";

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  // Pin the tracing root to this folder. Otherwise Next 15 picks the repo root when it
  // finds another lockfile there, which changes the standalone output layout.
  outputFileTracingRoot: fileURLToPath(new URL(".", import.meta.url)),
};

export default nextConfig;
