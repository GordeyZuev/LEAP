import type { ReactNode } from "react";
import Link from "next/link";
import Image from "next/image";

import { Footer } from "@/components/layout/footer";
import { PublicThemeButton } from "@/components/ui/theme-toggle";

export function ProductNewsPage({ title, description, children }: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <header className="border-b border-border bg-card">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4 sm:px-8">
          <Link href="/updates" className="flex items-center gap-2 text-sm font-semibold tracking-wider text-primary">
            <Image src="/logo_symb.svg" alt="" width={24} height={24} /> LEAP
          </Link>
          <PublicThemeButton />
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-5 py-8 sm:px-8 sm:py-12">
        <div className="mx-auto mb-6 max-w-xl text-center">
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{title}</h1>
          <p className="mt-2 text-sm text-muted-foreground">{description}</p>
        </div>
        {children}
      </main>
      <Footer variant="public" />
    </div>
  );
}
