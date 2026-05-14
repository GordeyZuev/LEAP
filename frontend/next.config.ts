import type { NextConfig } from "next";

const envOrigins =
  process.env.NEXT_DEV_ALLOWED_ORIGINS?.split(",")
    .map((origin) => origin.trim())
    .filter(Boolean) ?? [];

const nextConfig: NextConfig = {
  // LAN IPs for opening the dev app via Network URL (HMR / _next assets).
  // Add more comma-separated hosts in .env.local: NEXT_DEV_ALLOWED_ORIGINS=...
  allowedDevOrigins: [...new Set(["172.20.10.2", "10.214.134.149", "192.168.1.10", ...envOrigins])],
};

export default nextConfig;
