import type { Metadata } from "next";
import { EmbedView } from "./embed-view";

export const metadata: Metadata = { title: "LEAP video", robots: { index: false, follow: false } };

export default async function EmbedPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return <EmbedView token={token} />;
}
