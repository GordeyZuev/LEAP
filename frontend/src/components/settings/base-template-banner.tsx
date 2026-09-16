"use client";

import Link from "next/link";
import { ChevronRight, FileText } from "lucide-react";
import { formatBaseTemplateLabel } from "@/lib/base-template";
import { CARD_CHEVRON, CARD_INTERACTIVE, CARD_SHELL } from "@/components/ui/section-card";
import { cn } from "@/lib/utils";

interface BaseTemplateBannerProps {
  template?: { id: number; name: string } | null;
  loading?: boolean;
}

export function BaseTemplateBanner({ template, loading }: BaseTemplateBannerProps) {
  if (loading) {
    return (
      <div className={cn("h-[4.25rem] animate-pulse", CARD_SHELL)} />
    );
  }

  if (!template) return null;

  const label = formatBaseTemplateLabel(template.name);

  return (
    <Link
      href={`/templates/${template.id}`}
      className={cn("group flex items-center gap-4 px-5 py-4", CARD_SHELL, CARD_INTERACTIVE)}
    >
      <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
        <FileText size={18} aria-hidden />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Base template
        </span>
        <span className="mt-0.5 block truncate text-sm font-semibold text-foreground">{label}</span>
        <span className="mt-0.5 block text-xs text-muted-foreground">
          Default settings for video processing, metadata, and uploads
        </span>
      </span>
      <ChevronRight
        size={16}
        className={CARD_CHEVRON}
        aria-hidden
      />
    </Link>
  );
}
