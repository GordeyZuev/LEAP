"use client";

import { useId } from "react";
import { Sparkles } from "lucide-react";

import type { ProductUpdate } from "@/api/product-updates";
import { ActionButton } from "@/components/ui/action-button";
import { Modal } from "@/components/ui/modal";

interface ReleaseNotesModalProps {
  open: boolean;
  update: ProductUpdate;
  onDismiss: () => void;
}

function NoteSection({
  title,
  items,
}: {
  title: string;
  items: string[];
}) {
  if (items.length === 0) return null;

  return (
    <section>
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</h3>
      <ul className="space-y-3 text-sm leading-relaxed text-secondary-foreground">
        {items.map((item, index) => (
          <li key={index} className="flex gap-2.5">
            <span className="mt-2 size-1.5 shrink-0 rounded-full bg-primary" aria-hidden />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function ReleaseNotesModal({ open, update, onDismiss }: ReleaseNotesModalProps) {
  const titleId = useId();

  return (
    <Modal
      open={open}
      onClose={onDismiss}
      labelledBy={titleId}
      closeOnBackdrop={false}
      closeOnEsc={false}
      panelClassName="max-w-lg"
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
              What&apos;s new{update.version ? ` · v${update.version}` : ""}
            </p>
            <h2 id={titleId} className="mt-1 text-base font-semibold text-foreground">
              {update.title}
            </h2>
          </div>
        </div>

        <div className="mb-6 space-y-3 text-sm leading-relaxed text-secondary-foreground">
          <p>{update.summary}</p>
        </div>

        <div className="mb-6 space-y-5">
          <NoteSection title="For audience" items={update.audience_bullets} />
          <NoteSection title="For creators" items={update.creator_bullets} />
        </div>

        <div className="flex justify-end">
          <ActionButton variant="primary" onClick={onDismiss}>
            Got it
          </ActionButton>
        </div>
      </div>
    </Modal>
  );
}
