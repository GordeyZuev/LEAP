"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { useSession } from "@/hooks/use-session";
import { LandingPage } from "@/components/landing/landing-page";

export default function RootPage() {
  const router = useRouter();
  const status = useSession();

  useEffect(() => {
    if (status === "authenticated") router.replace("/recordings");
  }, [status, router]);

  if (status === "checking" || status === "authenticated") {
    return <div className="min-h-screen bg-[#FAFAFA]" />;
  }

  return <LandingPage />;
}
