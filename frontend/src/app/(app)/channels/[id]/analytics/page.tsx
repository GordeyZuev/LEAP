import { redirect } from "next/navigation";

export default async function ChannelAnalyticsRedirect({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  redirect(`/channels/${id}?tab=analytics`);
}
