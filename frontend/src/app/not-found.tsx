import Link from "next/link";
import { Logo } from "@/components/layout/logo";

export default function NotFound() {
  return (
    <div className="min-h-full flex items-center justify-center bg-[#FAFAFA] px-4">
      <div className="w-full max-w-md flex flex-col items-center text-center">
        <Logo size={40} />
        <p className="text-[88px] leading-none font-bold text-[#224C87] tracking-tight mt-10">
          404
        </p>
        <p className="text-sm text-gray-500 mt-4">
          The page you&apos;re looking for doesn&apos;t exist.
        </p>
        <Link
          href="/recordings"
          className="text-sm font-medium text-[#224C87] hover:underline mt-8"
        >
          Back to home
        </Link>
      </div>
    </div>
  );
}
