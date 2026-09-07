"use client";

import { useMemo, useState } from "react";

export type JinjaAcItem = { value: string; description: string };

export function useJinjaCombobox(items: JinjaAcItem[]) {
  const [acOpen, setAcOpen] = useState(false);
  const [acQuery, setAcQuery] = useState("");
  const [highlight, setHighlight] = useState(0);

  const filtered = useMemo(
    () => items.filter((v) => v.value.toLowerCase().startsWith(acQuery.toLowerCase())),
    [items, acQuery],
  );

  function updateFromCaret(text: string, caret: number) {
    if (!items.length) {
      setAcOpen(false);
      setAcQuery("");
      return;
    }
    const before = text.slice(0, caret);
    const match = before.match(/\{\{\s*(\w*)$/);
    if (match) {
      setAcOpen(true);
      setAcQuery(match[1]);
      setHighlight(0);
    } else {
      setAcOpen(false);
      setAcQuery("");
    }
  }

  function moveHighlight(delta: number) {
    if (!filtered.length) return;
    setHighlight((h) => (h + delta + filtered.length) % filtered.length);
  }

  const safeHighlight = filtered.length ? Math.min(highlight, filtered.length - 1) : 0;
  const active = filtered[safeHighlight];

  return {
    acOpen,
    setAcOpen,
    acQuery,
    filtered,
    highlight: safeHighlight,
    active,
    updateFromCaret,
    moveHighlight,
  };
}

export function insertJinjaVar(
  value: string,
  start: number,
  end: number,
  varName: string,
): { next: string; caret: number } {
  const before = value.slice(0, start);
  const after = value.slice(end);
  const newBefore = before.replace(/\{\{\s*\w*$/, `{{ ${varName} }}`);
  return { next: newBefore + after, caret: newBefore.length };
}
