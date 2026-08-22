"use client";

import Link from "next/link";
import { ChevronRight, FileText } from "lucide-react";
import { formatBaseTemplateLabel } from "@/lib/base-template";

interface BaseTemplateBannerProps {
  template?: { id: number; name: string } | null;
  loading?: boolean;
}

export function BaseTemplateBanner({ template, loading }: BaseTemplateBannerProps) {
  if (loading) {
    return (
      <div className="h-[4.25rem] animate-pulse rounded-2xl border border-border bg-card shadow-sm" />
    );
  }

  if (!template) return null;

  const label = formatBaseTemplateLabel(template.name);

  return (
    <Link
      href={`/templates/${template.id}`}
      className="group flex items-center gap-4 rounded-2xl border border-border bg-card px-5 py-4 shadow-sm transition-colors hover:border-primary/30 hover:bg-muted/30"
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
        className="shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary"
        aria-hidden
      />
    </Link>
  );
}
