"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { AlertTriangle } from "lucide-react";
import { useCredentialsNeedingReauth } from "@/hooks/use-credentials-reauth";

const PLATFORM_LABELS: Record<string, string> = {
  youtube: "YouTube",
  vk_video: "VK Video",
  zoom: "Zoom",
  yandex_disk: "Yandex Disk",
  mts_link: "MTS Link",
};

function platformLabel(platform: string): string {
  return PLATFORM_LABELS[platform] ?? platform;
}

function credentialLabel(item: { platform: string; account_name: string | null }): string {
  const platform = platformLabel(item.platform);
  const name = item.account_name?.trim();
  return name ? `${platform} (${name})` : platform;
}

function reauthMessage(
  items: { platform: string; account_name: string | null }[],
  total: number,
): string {
  if (total === 1 && items[0]) {
    return `Reconnect ${credentialLabel(items[0])} so downloads and uploads can continue.`;
  }
  if (total === 2 && items.length >= 2) {
    return `Reconnect ${credentialLabel(items[0])} and ${credentialLabel(items[1])} so downloads and uploads can continue.`;
  }
  return `${total} credentials need reconnection. Downloads and uploads will fail until you reconnect them.`;
}

export function CredentialReauthBanner() {
  const pathname = usePathname();
  const { data } = useCredentialsNeedingReauth();
  const items = data?.items ?? [];
  const total = data?.total ?? 0;

  if (total === 0) return null;
  if (pathname === "/credentials" || pathname.startsWith("/credentials/")) return null;

  return (
    <div className="px-6 pt-6 sm:px-8">
      <div
        role="status"
        className="flex flex-col gap-3 rounded-xl border border-warning-fg/40 bg-warning-fg/10 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
      >
        <p className="flex min-w-0 items-start gap-2.5 text-sm text-warning-fg">
          <AlertTriangle size={16} strokeWidth={2} className="mt-0.5 shrink-0" aria-hidden />
          <span>{reauthMessage(items, total)}</span>
        </p>
        <Link
          href="/credentials?sort_by=status&sort_order=asc"
          className="pressable inline-flex shrink-0 items-center justify-center rounded-xl border border-warning-fg/40 bg-card px-3 py-1.5 text-xs font-medium text-warning-fg hover:bg-warning-fg/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-warning-fg/30"
        >
          Reconnect credentials
        </Link>
      </div>
    </div>
  );
}
