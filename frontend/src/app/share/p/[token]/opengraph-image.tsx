import { fetchPublicPlaylistForMetadata } from "@/api/share";
import { OG_SIZE, shareOpenGraphImage } from "@/lib/share-og-image";

export const alt = "Shared playlist";
export const size = OG_SIZE;
export const contentType = "image/png";
export const revalidate = 300;

export default async function Image({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const playlist = await fetchPublicPlaylistForMetadata(token);
  return shareOpenGraphImage(
    `/api/v1/share/p/${token}/poster`,
    playlist?.name ?? "LEAP",
  );
}
