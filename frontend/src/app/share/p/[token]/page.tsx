import { Suspense } from "react";
import type { Metadata } from "next";

import { fetchPublicPlaylistForMetadata } from "@/api/share";

import { WatchShell } from "./watch-shell";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ token: string }>;
}): Promise<Metadata> {
  const { token } = await params;
  const playlist = await fetchPublicPlaylistForMetadata(token);

  if (!playlist) {
    return { title: "Shared playlist — LEAP", robots: { index: false, follow: false } };
  }

  return {
    title: `${playlist.name} — LEAP`,
    description: playlist.description || "Shared via LEAP",
    robots: { index: false, follow: false },
    openGraph: {
      type: "website",
      title: playlist.name,
      description: playlist.description || "Shared via LEAP",
      siteName: "LEAP",
    },
  };
}

export default async function PlaylistSharePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return (
    <Suspense fallback={null}>
      <WatchShell token={token} />
    </Suspense>
  );
}
