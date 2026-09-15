import { Suspense } from "react";
import type { Metadata } from "next";

import { fetchPublicChannelForMetadata } from "@/api/share";
import { formattedTextToPlain } from "@/lib/formatted-text";

import { ChannelPublicView } from "./channel-view";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const channel = await fetchPublicChannelForMetadata(slug);
  if (!channel) {
    return { title: "Shared channel – LEAP", robots: { index: false, follow: false } };
  }
  const description = channel.description ? formattedTextToPlain(channel.description) : "Shared via LEAP";
  return {
    title: `${channel.name} – LEAP`,
    description,
    robots: { index: false, follow: false },
    openGraph: {
      type: "website",
      title: channel.name,
      description,
      siteName: "LEAP",
      images: channel.banner_url ? [{ url: channel.banner_url }] : undefined,
    },
  };
}

export default async function PublicChannelPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return (
    <Suspense fallback={<div className="p-8 text-sm text-muted-foreground">Loading…</div>}>
      <ChannelPublicView slug={slug} />
    </Suspense>
  );
}
