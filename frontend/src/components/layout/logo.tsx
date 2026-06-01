import Image from "next/image";
import { cn } from "@/lib/utils";

// Source SVGs are 220×267 — keep aspect ratio so the mark never looks squashed.
const SYMBOL_ASPECT = 220 / 267;

interface LogoProps {
  /** Visual height in px. Width is derived from the symbol's aspect ratio. */
  size?: number;
  /** "default" = blue symbol on light bg. "inverse" = white symbol on dark bg. */
  variant?: "default" | "inverse";
  className?: string;
}

export function Logo({ size = 28, variant = "default", className }: LogoProps) {
  const src = variant === "inverse" ? "/logo_symb_inverse.svg" : "/logo_symb.svg";
  const width = Math.max(1, Math.round(size * SYMBOL_ASPECT));
  return (
    <Image
      src={src}
      alt="LEAP"
      width={width}
      height={size}
      priority
      className={cn("shrink-0", className)}
    />
  );
}
