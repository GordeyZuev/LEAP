import type { NextConfig } from "next";

const envOrigins =
  process.env.NEXT_DEV_ALLOWED_ORIGINS?.split(",")
    .map((origin) => origin.trim())
    .filter(Boolean) ?? [];

const nextConfig: NextConfig = {
  // Standalone output: builds a self-contained .next/standalone directory
  // (server.js + minimal node_modules) used by the Docker runtime stage.
  output: "standalone",
  // LAN IPs for HMR via Network URL. Set in .env.local: NEXT_DEV_ALLOWED_ORIGINS=ip1,ip2,...
  allowedDevOrigins: [...new Set(envOrigins)],
};

export default nextConfig;
