import type { Metadata } from "next";

import { fetchPublicRecordingForMetadata } from "@/api/share";
import { formatDuration } from "@/lib/utils";

import { ShareView } from "./share-view";

/**
 * Server shell. Its only job is `generateMetadata`: a share link is made to be
 * pasted into a chat, and without this every one of them previewed as the same
 * "LEAP — Shared Recording" with no hint of what was sent.
 */
export async function generateMetadata({
  params,
}: {
  params: Promise<{ token: string }>;
}): Promise<Metadata> {
  const { token } = await params;
  const recording = await fetchPublicRecordingForMetadata(token);

  // Revoked or unreachable: stay neutral rather than leak anything.
  if (!recording) {
    return { title: "Shared recording — LEAP", robots: { index: false, follow: false } };
  }

  const duration = recording.duration > 0 ? formatDuration(recording.duration) : null;
  const description = [duration, "Shared via LEAP"].filter(Boolean).join(" · ");

  return {
    title: `${recording.display_name} — LEAP`,
    description,
    // A share token is an unguessable capability URL; keep it out of indexes.
    robots: { index: false, follow: false },
    openGraph: {
      type: "video.other",
      title: recording.display_name,
      description,
      siteName: "LEAP",
    },
    twitter: {
      card: "summary_large_image",
      title: recording.display_name,
      description,
    },
  };
}

export default async function SharePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return <ShareView token={token} />;
}
