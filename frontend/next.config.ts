import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  output: "standalone",
  // Anchor the output file tracing root to the frontend directory itself.
  // This ensures standalone/server.js is placed at standalone/ root (not nested
  // inside a monorepo path like standalone/AgenticAIProject/frontend/) regardless
  // of what lockfiles exist in parent directories.
  outputFileTracingRoot: path.join(__dirname),
};

export default nextConfig;
