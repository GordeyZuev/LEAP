import { cookies } from "next/headers";

import type { UserMe } from "@/components/settings/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Current user for RSC layouts — forwards session cookies to the API. */
export async function fetchMeServer(): Promise<UserMe | null> {
  const jar = await cookies();
  const cookieHeader = jar
    .getAll()
    .map((c) => `${c.name}=${c.value}`)
    .join("; ");
  if (!cookieHeader) return null;

  try {
    const res = await fetch(`${API_URL}/api/v1/users/me`, {
      headers: { Cookie: cookieHeader },
      cache: "no-store",
    });
    if (!res.ok) return null;
    return (await res.json()) as UserMe;
  } catch {
    return null;
  }
}
