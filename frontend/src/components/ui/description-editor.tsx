"use client";

import { useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Info } from "lucide-react";
import { cn } from "@/lib/utils";
import { FILTER_CONTROL, FILTER_LABEL } from "@/lib/filter-field-classes";
import {
  applyDescriptionHotkey,
  DESCRIPTION_FORMAT_HINT,
  DESCRIPTION_FORMAT_WHISPER,
  isDescriptionFormatHotkey,
} from "@/lib/formatted-text";

export type JinjaVar = { value: string; description: string };

function syncHeight(ta: HTMLTextAreaElement) {
  ta.style.height = "auto";
  const lineHeight = parseFloat(getComputedStyle(ta).lineHeight) || 18;
  ta.style.height = `${ta.scrollHeight + lineHeight}px`;
}

export function DescriptionEditor({
  id,
  label,
  value,
  onChange,
  placeholder,
  rows = 5,
  variables = [],
  hint,
  className,
}: {
  id?: string;
  label?: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  rows?: number;
  variables?: JinjaVar[];
  hint?: string;
  className?: string;
}) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const blurTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const generatedId = useId();
  const fieldId = id ?? generatedId;
  const listboxId = useId();
  const [acOpen, setAcOpen] = useState(false);
  const [acQuery, setAcQuery] = useState("");

  const filtered = useMemo(
    () =>
      variables.filter((v) => v.value.toLowerCase().startsWith(acQuery.toLowerCase())),
    [variables, acQuery],
  );

  useLayoutEffect(() => {
    if (textareaRef.current) syncHeight(textareaRef.current);
  }, [value]);

  function updateAc(text: string, caret: number) {
    if (!variables.length) {
      setAcOpen(false);
      return;
    }
    const before = text.slice(0, caret);
    const match = before.match(/\{\{\s*(\w*)$/);
    if (match) {
      setAcOpen(true);
      setAcQuery(match[1]);
    } else {
      setAcOpen(false);
      setAcQuery("");
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (!(e.metaKey || e.ctrlKey) || e.altKey) return;
    if (!isDescriptionFormatHotkey(e.code, e.shiftKey)) return;
    e.preventDefault();
    const ta = e.currentTarget;
    const applied = applyDescriptionHotkey(e.code, e.shiftKey, ta.value, ta.selectionStart, ta.selectionEnd);
    if (!applied || applied.next === ta.value) return;
    onChange(applied.next);
    const [a, b] = applied.range;
    requestAnimationFrame(() => {
      textareaRef.current?.focus();
      textareaRef.current?.setSelectionRange(a, b);
    });
  }

  function insertVar(varName: string) {
    const ta = textareaRef.current;
    if (!ta) return;
    const caret = ta.selectionStart;
    const before = value.slice(0, caret);
    const after = value.slice(ta.selectionEnd);
    const newBefore = before.replace(/\{\{\s*\w*$/, `{{ ${varName} }}`);
    const newVal = newBefore + after;
    onChange(newVal);
    setAcOpen(false);
    requestAnimationFrame(() => {
      textareaRef.current?.focus();
      textareaRef.current?.setSelectionRange(newBefore.length, newBefore.length);
    });
  }

  return (
    <div className={cn("space-y-1", className)}>
      {label ? (
        <label htmlFor={fieldId} className={FILTER_LABEL}>
          {label}
        </label>
      ) : null}
      <div className="relative">
        <textarea
          ref={textareaRef}
          id={fieldId}
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
            updateAc(e.target.value, e.target.selectionStart);
          }}
          onKeyDown={handleKeyDown}
          onSelect={(e) => updateAc(value, e.currentTarget.selectionStart)}
          onBlur={() => {
            blurTimer.current = setTimeout(() => setAcOpen(false), 150);
          }}
          rows={rows}
          placeholder={placeholder}
          spellCheck
          className={cn(
            FILTER_CONTROL,
            "min-h-[2.875rem] max-h-[40vh] w-full resize-y whitespace-pre-wrap break-words px-3 py-2.5 text-sm leading-relaxed",
          )}
        />
        {acOpen && filtered.length > 0 && (
          <ul
            id={listboxId}
            role="listbox"
            className="absolute left-0 right-0 top-full z-50 mt-1 max-h-44 overflow-y-auto rounded-xl border border-border bg-card shadow-lg"
          >
            {filtered.map((v) => (
              <li key={v.value} role="option" aria-selected={false}>
                <button
                  type="button"
                  onMouseDown={(ev) => {
                    ev.preventDefault();
                    if (blurTimer.current) clearTimeout(blurTimer.current);
                    insertVar(v.value);
                  }}
                  className="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-muted"
                >
                  <code className="shrink-0 font-mono text-xs text-primary">{`{{ ${v.value} }}`}</code>
                  <span className="text-xs text-muted-foreground">{v.description}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <p className="flex items-start gap-1 text-[11px] text-muted-foreground">
        <Info size={11} className="mt-0.5 shrink-0" />
        <span>
          {hint ?? DESCRIPTION_FORMAT_HINT}
          {variables.length > 0 ? (
            <>
              {" "}
              Type <code className="font-mono">{"{{ "}</code> for{" "}
              {variables.map((v) => v.value).join(", ")}.
            </>
          ) : null}
        </span>
      </p>
      <p className="pl-4 text-[10px] leading-snug text-muted-foreground/55">{DESCRIPTION_FORMAT_WHISPER}</p>
    </div>
  );
}
