"use client";

import type { ReactNode } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { Tabs, type TabItem } from "@/components/ui/tabs";

type AdminSection = "overview" | "users" | "plans" | "news" | "feedback" | "audit";

const SECTIONS: TabItem<AdminSection>[] = [
  { value: "overview", label: "Overview" },
  { value: "users", label: "Users" },
  { value: "plans", label: "Plans" },
  { value: "news", label: "News & email" },
  { value: "feedback", label: "Feedback" },
  { value: "audit", label: "Audit log" },
];

const MAIN_SECTIONS = new Set<AdminSection>(["overview", "users", "plans", "audit"]);

function isAdminSection(value: string | null): value is AdminSection {
  return SECTIONS.some((section) => section.value === value);
}

export function AdminSections({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const isNewsPage = pathname.startsWith("/admin/updates");
  const requestedSection = searchParams.get("section");
  const section: AdminSection = isNewsPage
    ? requestedSection === "feedback" ? "feedback" : "news"
    : isAdminSection(requestedSection) && MAIN_SECTIONS.has(requestedSection)
      ? requestedSection
      : "overview";

  function navigate(next: AdminSection) {
    const href = next === "news"
      ? "/admin/updates"
      : next === "feedback"
        ? "/admin/updates?section=feedback"
        : next === "overview"
          ? "/admin"
          : `/admin?section=${next}`;
    router.replace(href, { scroll: false });
  }

  return (
    <Tabs items={SECTIONS} value={section} onChange={navigate} label="Admin sections">
      {children}
    </Tabs>
  );
}
