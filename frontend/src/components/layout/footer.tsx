import Link from "next/link";

import { APP_VERSION } from "@/lib/app-version";

const VERSION = APP_VERSION;

const LINKS = [
  { label: "News & Updates", href: "/updates" },
  { label: "Contact & Feedback", href: "/updates/feedback" },
] as const;

export function Footer() {
  return (
    <footer className="border-t border-border bg-card">
      <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 px-5 py-4 text-xs text-muted-foreground">
        <span>© {new Date().getFullYear()} LEAP</span>
        <span className="text-muted-foreground/40" aria-hidden>·</span>
        <span>12+</span>
        <span className="text-muted-foreground/40" aria-hidden>·</span>
        <span>v{VERSION}</span>
        <span className="text-muted-foreground/40" aria-hidden>·</span>
        {LINKS.map(({ label, href }, index) => (
          <span key={href} className="contents">
            {index > 0 && <span className="text-muted-foreground/40" aria-hidden>·</span>}
            <Link href={href} className="transition-colors hover:text-primary">
              {label}
            </Link>
          </span>
        ))}
      </div>
    </footer>
  );
}
