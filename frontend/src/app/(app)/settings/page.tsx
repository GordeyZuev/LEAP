"use client";

import { Suspense, useCallback, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { PageHeader } from "@/components/ui/page-header";
import { Tabs, type TabItem } from "@/components/ui/tabs";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Field } from "@/components/ui/field";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { SectionCard } from "@/components/settings/shared";
import { AccountPanel } from "@/components/settings/account-panel";
import { ProcessingPanel } from "@/components/settings/processing-panel";
import { SecurityPanel } from "@/components/settings/security-panel";

type Tab = "account" | "appearance" | "processing" | "security";

const TABS: TabItem<Tab>[] = [
  { value: "account", label: "Account" },
  { value: "appearance", label: "Appearance" },
  { value: "processing", label: "Processing" },
  { value: "security", label: "Security" },
];

const IS_TAB = (v: string | null): v is Tab => TABS.some((t) => t.value === v);

function SettingsContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const raw = searchParams.get("tab");
  const tab: Tab = IS_TAB(raw) ? raw : "account";

  // Switching tabs unmounts the Processing panel, which would silently drop its
  // unsaved edits — so the move has to be confirmed while it is dirty.
  const [processingDirty, setProcessingDirty] = useState(false);
  const [pendingTab, setPendingTab] = useState<Tab | null>(null);

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

  const onChange = useCallback(
    (next: Tab) => {
      if (next === tab) return;
      if (tab === "processing" && processingDirty) {
        setPendingTab(next);
        return;
      }
      goTo(next);
    },
    [tab, processingDirty, goTo],
  );

  return (
    <div className="w-full min-w-0 p-6 sm:p-8">
      <PageHeader title="Settings" />

      <Tabs items={TABS} value={tab} onChange={onChange} label="Settings sections">
        {tab === "account" && <AccountPanel />}
        {tab === "appearance" && (
          <SectionCard title="Appearance">
            <Field label="Theme" hint="Choose a light or dark interface, or follow your system setting.">
              <ThemeToggle />
            </Field>
          </SectionCard>
        )}
        {/* Kept mounted across tabs would preserve edits, but it also keeps a
            fixed save bar on screen for a panel you can no longer see. */}
        {tab === "processing" && <ProcessingPanel onDirtyChange={setProcessingDirty} />}
        {tab === "security" && <SecurityPanel />}
      </Tabs>

      <ConfirmDialog
        open={pendingTab !== null}
        title="Leave without saving?"
        description="Processing defaults has unsaved changes. Leaving this tab discards them."
        confirmLabel="Discard and leave"
        cancelLabel="Stay here"
        danger
        onConfirm={() => {
          const next = pendingTab;
          setPendingTab(null);
          setProcessingDirty(false);
          if (next) goTo(next);
        }}
        onCancel={() => setPendingTab(null)}
      />
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
