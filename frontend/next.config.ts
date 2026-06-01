import os from "os";

import type { NextConfig } from "next";

function getLanAddresses(): string[] {
  const addresses: string[] = [];
  for (const iface of Object.values(os.networkInterfaces())) {
    if (!iface) continue;
    for (const config of iface) {
      const isIpv4 = String(config.family) === "IPv4";
      if (isIpv4 && !config.internal) {
        addresses.push(config.address);
      }
    }
  }
  return addresses;
}

const envOrigins =
  process.env.NEXT_DEV_ALLOWED_ORIGINS?.split(",")
    .map((origin) => origin.trim())
    .filter(Boolean) ?? [];

const nextConfig: NextConfig = {
  output: "standalone",
  allowedDevOrigins: [...new Set([...getLanAddresses(), ...envOrigins])],
  images: {
    dangerouslyAllowSVG: true,
    contentSecurityPolicy: "default-src 'self'; script-src 'none'; sandbox;",
  },
};

export default nextConfig;
