import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Required for Dockerfile.web (copies `.next/standalone` into a slim runtime image)
  output: "standalone",
};

export default nextConfig;
