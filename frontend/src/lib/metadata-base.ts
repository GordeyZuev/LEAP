/** Public origin for absolute Open Graph image URLs. */
export function metadataBaseFromHeaders(headerList: { get(name: string): string | null }): URL {
  const rawHost = headerList.get("host") ?? "";
  const host = rawHost.split(",")[0]?.trim() ?? "";
  const forwarded = headerList.get("x-forwarded-proto")?.split(",")[0]?.trim();
  const local = host.length === 0 || host.startsWith("localhost") || host.startsWith("127.0.0.1") || host.startsWith("[::1]");
  const proto = forwarded === "http" || forwarded === "https" ? forwarded : local ? "http" : "https";
  try {
    const url = new URL(`${proto}://${host || "localhost:3000"}`);
    if (url.username || url.password || url.pathname !== "/" || url.search || url.hash) {
      return new URL("http://localhost:3000");
    }
    return new URL(`${url.protocol}//${url.host}`);
  } catch {
    return new URL("http://localhost:3000");
  }
}
