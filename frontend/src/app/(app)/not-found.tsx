import Link from "next/link";
import { Logo } from "@/components/layout/logo";

export default function AppNotFound() {
  return (
    <div className="flex h-full items-center justify-center bg-background px-4">
      <div className="flex w-full max-w-md flex-col items-center text-center">
        <Link href="/home" aria-label="LEAP — home">
          <Logo size={40} />
        </Link>
        <p className="mt-10 text-[88px] font-bold leading-none tracking-tight text-primary">404</p>
        <p className="mt-4 text-sm text-muted-foreground">This page doesn&apos;t exist in LEAP.</p>
        <Link
          href="/home"
          className="mt-8 text-sm font-medium text-primary hover:underline"
        >
          Back to home
        </Link>
      </div>
    </div>
  );
}
