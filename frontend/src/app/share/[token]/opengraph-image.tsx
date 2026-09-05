import { fetchPublicRecordingForMetadata } from "@/api/share";
import { OG_SIZE, shareOpenGraphImage } from "@/lib/share-og-image";

export const alt = "Shared recording";
export const size = OG_SIZE;
export const contentType = "image/png";
export const revalidate = 300;

export default async function Image({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const recording = await fetchPublicRecordingForMetadata(token);
  return shareOpenGraphImage(
    `/api/v1/share/${token}/poster`,
    recording?.display_name ?? "LEAP",
  );
}
