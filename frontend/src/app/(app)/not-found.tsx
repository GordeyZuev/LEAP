import Link from "next/link";
import { Logo } from "@/components/layout/logo";

export default function AppNotFound() {
  return (
    <div className="flex h-full items-center justify-center bg-[#FAFAFA] px-4">
      <div className="flex w-full max-w-md flex-col items-center text-center">
        <Logo size={40} />
        <p className="mt-10 text-[88px] font-bold leading-none tracking-tight text-[#224C87]">404</p>
        <p className="mt-4 text-sm text-gray-500">This page doesn&apos;t exist in LEAP.</p>
        <Link
          href="/recordings"
          className="mt-8 text-sm font-medium text-[#224C87] hover:underline"
        >
          Back to recordings
        </Link>
      </div>
    </div>
  );
}
