import { NextResponse, type NextRequest } from "next/server";

/** Only the dedicated player page may be framed by configured website origins. */
export function proxy(_request: NextRequest) {
  const origins = (process.env.EMBED_ALLOWED_ORIGINS ?? "")
    .split(",")
    .map((value) => value.trim())
    .filter((value) => {
      try {
        const url = new URL(value);
        return url.protocol === "https:" && url.origin === value;
      } catch {
        return false;
      }
    });
  const response = NextResponse.next();
  response.headers.set("Content-Security-Policy", `frame-ancestors 'self' ${origins.join(" ")}`.trim());
  return response;
}

export const config = { matcher: "/embed/:path*" };
