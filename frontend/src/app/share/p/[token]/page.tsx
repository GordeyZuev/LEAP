import { Suspense, cache } from "react";
import type { Metadata } from "next";

import { fetchPublicPlaylistForMetadata } from "@/api/share";
import { formattedTextToPlain } from "@/lib/formatted-text";

import { WatchShell } from "./watch-shell";

const loadPlaylist = cache(fetchPublicPlaylistForMetadata);

export async function generateMetadata({
  params,
  searchParams,
}: {
  params: Promise<{ token: string }>;
  searchParams: Promise<{ v?: string }>;
}): Promise<Metadata> {
  const { token } = await params;
  const { v } = await searchParams;
  const playlist = await loadPlaylist(token, v ? "catalog" : "full");

  if (!playlist) {
    return { title: "Shared playlist – LEAP", robots: { index: false, follow: false } };
  }

  return {
    title: `${playlist.name} – LEAP`,
    description: playlist.description ? formattedTextToPlain(playlist.description) : "Shared via LEAP",
    robots: { index: false, follow: false },
    openGraph: {
      type: "website",
      title: playlist.name,
      description: playlist.description ? formattedTextToPlain(playlist.description) : "Shared via LEAP",
      siteName: "LEAP",
    },
  };
}

export default async function PlaylistSharePage({
  params,
  searchParams,
}: {
  params: Promise<{ token: string }>;
  searchParams: Promise<{ v?: string }>;
}) {
  const { token } = await params;
  const { v } = await searchParams;
  const playlistView = v ? "catalog" : "full";
  const initialPlaylist = await loadPlaylist(token, playlistView);
  return (
    <Suspense fallback={null}>
      <WatchShell token={token} initialPlaylist={initialPlaylist} initialView={playlistView} />
    </Suspense>
  );
}
