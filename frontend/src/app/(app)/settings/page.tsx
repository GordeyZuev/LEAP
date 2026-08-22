"use client";

import { Suspense, useCallback, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/ui/page-header";
import { Tabs, type TabItem } from "@/components/ui/tabs";
import { Field } from "@/components/ui/field";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { SectionCard } from "@/components/settings/shared";
import { BaseTemplateBanner } from "@/components/settings/base-template-banner";
import { AccountPanel } from "@/components/settings/account-panel";
import { RetentionSection } from "@/components/settings/retention-section";
import { SecurityPanel } from "@/components/settings/security-panel";
import { apiClient } from "@/api/client";

type Tab = "account" | "appearance" | "security";

const TABS: TabItem<Tab>[] = [
  { value: "account", label: "Account" },
  { value: "appearance", label: "Appearance" },
  { value: "security", label: "Security" },
];

const IS_TAB = (v: string | null): v is Tab => TABS.some((t) => t.value === v);

function SettingsContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const raw = searchParams.get("tab");
  const tab: Tab = IS_TAB(raw) ? raw : "account";

  const { data: defaultTemplate, isLoading: defaultTemplateLoading } = useQuery<{
    id: number;
    name: string;
  }>({
    queryKey: ["default-template"],
    queryFn: async () => (await apiClient.get("/templates/default")).data,
  });

  // Legacy ?tab=processing links → Account (base template lives there now).
  useEffect(() => {
    if (raw === "processing") {
      router.replace(window.location.pathname, { scroll: false });
    }
  }, [raw, router]);

  const goTo = useCallback(
    (next: Tab) => {
      const p = new URLSearchParams(window.location.search);
      if (next === "account") p.delete("tab");
      else p.set("tab", next);
      const qs = p.toString();
      router.replace(qs ? `?${qs}` : window.location.pathname, { scroll: false });
    },
    [router],
  );

  return (
    <div className="w-full min-w-0 p-6 sm:p-8">
      <PageHeader title="Settings" />

      <Tabs items={TABS} value={tab} onChange={goTo} label="Settings sections">
        {tab === "account" && (
          <div className="space-y-6">
            <BaseTemplateBanner template={defaultTemplate ?? null} loading={defaultTemplateLoading} />
            <AccountPanel />
            <SectionCard title="Data retention">
              <RetentionSection />
            </SectionCard>
          </div>
        )}
        {tab === "appearance" && (
          <SectionCard title="Appearance">
            <Field label="Theme" hint="Choose a light or dark interface, or follow your system setting.">
              <ThemeToggle />
            </Field>
          </SectionCard>
        )}
        {tab === "security" && <SecurityPanel />}
      </Tabs>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <Suspense fallback={<div className="p-8 text-sm text-muted-foreground">Loading settings…</div>}>
      <SettingsContent />
    </Suspense>
  );
}
