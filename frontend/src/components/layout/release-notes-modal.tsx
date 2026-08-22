"use client";

import Link from "next/link";
import { useId } from "react";
import { Sparkles } from "lucide-react";

import type { ReleaseNoteHighlight, ReleaseNotesContent } from "@/content/release-notes";
import { ActionButton } from "@/components/ui/action-button";
import { Modal } from "@/components/ui/modal";

interface ReleaseNotesModalProps {
  open: boolean;
  version: string;
  content: ReleaseNotesContent;
  onDismiss: () => void;
}

function HighlightLine({
  highlight,
  onNavigate,
}: {
  highlight: ReleaseNoteHighlight;
  onNavigate: () => void;
}) {
  return (
    <span>
      {highlight.parts.map((part, index) => {
        if (part.kind === "text") {
          return <span key={index}>{part.value}</span>;
        }
        return (
          <Link
            key={index}
            href={part.href}
            onClick={onNavigate}
            className="font-medium text-primary underline-offset-2 hover:underline"
          >
            {part.label}
          </Link>
        );
      })}
    </span>
  );
}

export function ReleaseNotesModal({ open, version, content, onDismiss }: ReleaseNotesModalProps) {
  const titleId = useId();

  return (
    <Modal
      open={open}
      onClose={onDismiss}
      labelledBy={titleId}
      closeOnBackdrop={false}
      closeOnEsc={false}
      panelClassName="max-w-md"
    >
      <div className="p-6">
        <div className="mb-4 flex items-start gap-3">
          <div
            className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary"
            aria-hidden
          >
            <Sparkles size={20} />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              What&apos;s new · v{version}
            </p>
            <h2 id={titleId} className="mt-1 text-base font-semibold text-foreground">
              {content.title}
            </h2>
          </div>
        </div>

        <ul className="mb-6 space-y-3 text-sm leading-relaxed text-secondary-foreground">
          {content.highlights.map((highlight, index) => (
            <li key={index} className="flex gap-2.5">
              <span className="mt-2 size-1.5 shrink-0 rounded-full bg-primary" aria-hidden />
              <HighlightLine highlight={highlight} onNavigate={onDismiss} />
            </li>
          ))}
        </ul>

        <div className="flex justify-end">
          <ActionButton variant="primary" onClick={onDismiss}>
            Got it
          </ActionButton>
        </div>
      </div>
    </Modal>
  );
}
