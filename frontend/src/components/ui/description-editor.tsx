"use client";

import { useId, useLayoutEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import { FILTER_CONTROL, FILTER_LABEL } from "@/lib/filter-field-classes";
import { applyDescriptionHotkey, isDescriptionFormatHotkey } from "@/lib/formatted-text";
import { AboutFormatting } from "@/components/ui/about-formatting";
import { insertJinjaVar, useJinjaCombobox } from "@/hooks/use-jinja-combobox";

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
  const optionIdPrefix = useId();
  const ac = useJinjaCombobox(variables);

  useLayoutEffect(() => {
    if (textareaRef.current) syncHeight(textareaRef.current);
  }, [value]);

  function commitInsert(varName: string) {
    const ta = textareaRef.current;
    if (!ta) return;
    const { next, caret } = insertJinjaVar(value, ta.selectionStart, ta.selectionEnd, varName);
    onChange(next);
    ac.setAcOpen(false);
    requestAnimationFrame(() => {
      textareaRef.current?.focus();
      textareaRef.current?.setSelectionRange(caret, caret);
    });
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    const listOpen = ac.acOpen && ac.filtered.length > 0;
    if (listOpen) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        ac.moveHighlight(1);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        ac.moveHighlight(-1);
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        if (ac.active) {
          e.preventDefault();
          commitInsert(ac.active.value);
        }
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        ac.setAcOpen(false);
        return;
      }
    }
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
            ac.updateFromCaret(e.target.value, e.target.selectionStart);
          }}
          onKeyDown={handleKeyDown}
          onSelect={(e) => ac.updateFromCaret(value, e.currentTarget.selectionStart)}
          onBlur={() => {
            blurTimer.current = setTimeout(() => ac.setAcOpen(false), 150);
          }}
          rows={rows}
          placeholder={placeholder}
          spellCheck
          aria-autocomplete="list"
          aria-expanded={ac.acOpen && ac.filtered.length > 0}
          aria-controls={ac.acOpen && ac.filtered.length > 0 ? listboxId : undefined}
          aria-activedescendant={
            ac.acOpen && ac.active ? `${optionIdPrefix}-${ac.active.value}` : undefined
          }
          className={cn(
            FILTER_CONTROL,
            "min-h-[2.875rem] max-h-[40vh] w-full resize-y whitespace-pre-wrap break-words px-3 py-2.5 text-sm leading-relaxed",
          )}
        />
        {ac.acOpen && ac.filtered.length > 0 && (
          <ul
            id={listboxId}
            role="listbox"
            className="absolute left-0 right-0 top-full z-50 mt-1 max-h-44 overflow-y-auto rounded-xl border border-border bg-card shadow-lg"
          >
            {ac.filtered.map((v) => (
              <li
                key={v.value}
                id={`${optionIdPrefix}-${v.value}`}
                role="option"
                aria-selected={ac.active?.value === v.value}
              >
                <button
                  type="button"
                  onMouseDown={(ev) => {
                    ev.preventDefault();
                    if (blurTimer.current) clearTimeout(blurTimer.current);
                    commitInsert(v.value);
                  }}
                  className={cn(
                    "flex w-full items-center gap-3 px-3 py-2 text-left",
                    ac.active?.value === v.value ? "bg-muted" : "hover:bg-muted",
                  )}
                >
                  <code className="shrink-0 font-mono text-xs text-primary">{`{{ ${v.value} }}`}</code>
                  <span className="text-xs text-muted-foreground">{v.description}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
      <AboutFormatting multiline />
    </div>
  );
}
