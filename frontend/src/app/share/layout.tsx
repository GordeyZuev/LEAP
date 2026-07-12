import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "LEAP — Shared Recording",
};

export default function ShareLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
