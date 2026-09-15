"use client";

import { Check, ExternalLink, Link as LinkIcon } from "lucide-react";

import { ActionButton } from "@/components/ui/action-button";
import { CARD_SHELL } from "@/components/ui/section-card";
import { cn } from "@/lib/utils";

const ACCESS_LINK =
  "inline-flex min-h-7 items-center gap-0.5 text-xs font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 rounded-sm";
const ACCESS_ACTION =
  "inline-flex min-h-7 items-center text-xs font-medium text-muted-foreground transition-colors hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 rounded-sm";

export function ShareAccessCard({
  headingId,
  title = "LEAP Link",
  active,
  hasToken,
  publicUrl,
  copied,
  enablePending,
  onCopy,
  onEnable,
  onDisable,
  onRotate,
  showRotate = false,
  hintActive,
  hintDisabled,
  hintNever,
}: {
  headingId: string;
  title?: string;
  active: boolean;
  hasToken: boolean;
  publicUrl: string | null;
  copied: boolean;
  enablePending: boolean;
  onCopy: () => void;
  onEnable: () => void;
  onDisable: () => void;
  onRotate?: () => void;
  showRotate?: boolean;
  hintActive: string;
  hintDisabled: string;
  hintNever: string;
}) {
  return (
    <section aria-labelledby={headingId} className={cn(CARD_SHELL, "overflow-hidden p-4")}>
      <div className="flex items-start gap-2.5">
        <span className="mt-px flex h-8 w-3.5 shrink-0 items-center justify-center" aria-hidden>
          {active ? (
            <Check size={14} className="text-success-fg" />
          ) : (
            <LinkIcon size={14} className="text-muted-foreground" />
          )}
        </span>
        <div className="min-w-0 flex-1">
          <h2 id={headingId} className="text-xs font-semibold text-foreground">
            {title}
          </h2>
          <p className={cn("text-xs", active ? "text-success-fg" : "text-muted-foreground")}>
            {active ? "Active" : "Not shared"}
          </p>
          {!active && (
            <div className="mt-3">
              <ActionButton
                size="sm"
                variant="primary"
                icon={<LinkIcon size={12} />}
                isPending={enablePending}
                onClick={onEnable}
                className="w-full justify-center"
              >
                Enable link
              </ActionButton>
            </div>
          )}
          {(active || hasToken) && (
            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-0.5">
              {active && publicUrl && (
                <>
                  <button type="button" onClick={onCopy} className={ACCESS_LINK}>
                    {copied ? "Copied" : "Copy"}
                  </button>
                  <a href={publicUrl} target="_blank" rel="noopener noreferrer" className={ACCESS_LINK}>
                    Open <ExternalLink size={10} aria-hidden />
                  </a>
                  <button type="button" onClick={onDisable} className={ACCESS_ACTION}>
                    Disable link
                  </button>
                </>
              )}
              {showRotate && hasToken && onRotate && (
                <button type="button" onClick={onRotate} className={ACCESS_ACTION}>
                  Rotate link
                </button>
              )}
            </div>
          )}
          <p className="mt-3 text-xs leading-snug text-muted-foreground">
            {active ? hintActive : hasToken ? hintDisabled : hintNever}
          </p>
        </div>
      </div>
    </section>
  );
}
