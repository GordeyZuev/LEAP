import { ImageResponse } from "next/og";

import { serverApiBase } from "@/api/share";

export const OG_SIZE = { width: 1200, height: 630 };

export async function shareOpenGraphImage(posterPath: string, title: string): Promise<ImageResponse> {
  let photo: string | null = null;
  try {
    const res = await fetch(`${serverApiBase()}${posterPath}`, {
      redirect: "follow",
      cache: "no-store",
    });
    const contentType = res.headers.get("content-type") ?? "";
    if (res.ok && contentType.startsWith("image/")) {
      const buf = Buffer.from(await res.arrayBuffer());
      photo = `data:${contentType};base64,${buf.toString("base64")}`;
    }
  } catch {
    // Title card below — crawlers still get an image.
  }

  return new ImageResponse(
    (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          width: "100%",
          height: "100%",
          background: "#0f172a",
          color: "#f8fafc",
          fontSize: 48,
          fontWeight: 600,
          textAlign: "center",
        }}
      >
        {photo ? (
          // eslint-disable-next-line @next/next/no-img-element -- next/og canvas
          <img
            src={photo}
            alt=""
            width={OG_SIZE.width}
            height={OG_SIZE.height}
            style={{ objectFit: "cover", width: "100%", height: "100%" }}
          />
        ) : (
          <div style={{ display: "flex", padding: 64 }}>{title}</div>
        )}
      </div>
    ),
    { ...OG_SIZE },
  );
}
