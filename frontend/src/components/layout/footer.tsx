import Link from "next/link";
import { Fragment } from "react";

const VERSION = process.env.NEXT_PUBLIC_APP_VERSION ?? "0.10.5.0";

const links = [
  { label: "Documentation", href: "/docs", external: false },
  { label: "Contact", href: "mailto:gordey.zuev@gmail.com", external: true },
];

export function Footer() {
  return (
    <footer className="border-t border-border bg-card">
      <div className="px-8 py-4 flex items-center justify-center gap-3 text-xs text-muted-foreground">
        <span>© {new Date().getFullYear()} LEAP</span>
        <span className="text-gray-200">·</span>
        <span className="text-gray-300">v{VERSION}</span>
        <span className="text-gray-200">·</span>
        {links.map(({ label, href, external }, i) => (
          <Fragment key={label}>
            {external ? (
              <a href={href} className="hover:text-primary transition-colors">
                {label}
              </a>
            ) : (
              <Link href={href} className="hover:text-primary transition-colors">
                {label}
              </Link>
            )}
            {i < links.length - 1 && <span className="text-gray-200">·</span>}
          </Fragment>
        ))}
      </div>
    </footer>
  );
}
