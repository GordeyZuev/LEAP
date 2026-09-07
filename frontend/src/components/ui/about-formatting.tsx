"use client";

import { useId, useState } from "react";
import { DESCRIPTION_FORMAT_HINT, DESCRIPTION_FORMAT_WHISPER } from "@/lib/formatted-text";

export function AboutFormatting({ multiline = false }: { multiline?: boolean }) {
  const [open, setOpen] = useState(false);
  const bodyId = useId();
  return (
    <div className="text-xs text-muted-foreground">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={bodyId}
        className="font-medium text-secondary-foreground underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
      >
        About formatting
      </button>
      {open && (
        <div id={bodyId} className="mt-1.5 space-y-1 leading-snug">
          <p>
            Type <code className="font-mono">{"{{ "}</code> to autocomplete variables.
            {multiline ? ` ${DESCRIPTION_FORMAT_HINT}` : null}
          </p>
          {multiline ? <p>{DESCRIPTION_FORMAT_WHISPER}</p> : null}
        </div>
      )}
    </div>
  );
}
