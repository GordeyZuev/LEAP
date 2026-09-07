"use client";

import { useId, useMemo, useState, type ReactNode } from "react";
import { X } from "lucide-react";

import { ActionButton } from "@/components/ui/action-button";
import { Modal } from "@/components/ui/modal";
import { cn } from "@/lib/utils";
import { CHECKBOX, FILTER_CONTROL } from "@/lib/filter-field-classes";
import { SegmentedField } from "@/components/ui/segmented-field";

export interface ChecklistItem<V extends string | number = number> {
  value: V;
  label: string;
  hint?: string;
  /** Type/platform chip. Distinct values become filters. */
  group?: string;
}

function formatGroupLabel(g: string) {
  if (/youtube/i.test(g)) return "YouTube";
  return g.replaceAll("_", " ").replace(/\w+/g, (word) => {
    if (word.toUpperCase() === "MTS") return "MTS";
    return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
  }  );
}

function ChecklistPickerPanel<V extends string | number>({
  items,
  value,
  onChange,
  searchPlaceholder,
  footer,
  showClear,
}: {
  items: ChecklistItem<V>[];
  value: V[];
  onChange: (next: V[]) => void;
  searchPlaceholder: string;
  footer?: ReactNode;
  showClear: boolean;
}) {
  const [query, setQuery] = useState("");
  const [group, setGroup] = useState<string | null>(null);
  const selected = useMemo(() => new Set(value), [value]);

  const groups = useMemo(() => {
    const seen = new Set<string>();
    for (const it of items) {
      if (it.group) seen.add(it.group);
    }
    return [...seen].sort((a, b) => a.localeCompare(b));
  }, [items]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return items.filter((it) => {
      if (group && it.group !== group) return false;
      if (!needle) return true;
      return (
        it.label.toLowerCase().includes(needle) ||
        (it.hint?.toLowerCase().includes(needle) ?? false) ||
        (it.group?.toLowerCase().includes(needle) ?? false)
      );
    });
  }, [items, query, group]);

  return (
    <>
      <div className="space-y-3 border-b border-border px-5 py-3">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={searchPlaceholder}
          aria-label={searchPlaceholder}
          className={FILTER_CONTROL}
        />
        {groups.length > 1 && (
          <SegmentedField
            stretch
            labelHidden
            label="Filter by type"
            value={group ?? ""}
            options={[
              { value: "", label: "All" },
              ...groups.map((g) => ({ value: g, label: formatGroupLabel(g) })),
            ]}
            onChange={(v) => setGroup(v === "" ? null : v)}
          />
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {filtered.length === 0 ? (
          <p className="px-3 py-8 text-center text-sm text-muted-foreground">Nothing matches</p>
        ) : (
          <ul className="space-y-0.5">
            {filtered.map((it) => {
              const checked = selected.has(it.value);
              return (
                <li key={String(it.value)}>
                  <label className="flex min-h-11 cursor-pointer items-center gap-3 rounded-xl px-3 py-2 hover:bg-muted">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() =>
                        onChange(checked ? value.filter((x) => x !== it.value) : [...value, it.value])
                      }
                      className={CHECKBOX}
                    />
                    <span className="min-w-0 flex-1 truncate text-sm font-medium text-foreground">{it.label}</span>
                    {it.hint ? <span className="shrink-0 text-xs text-muted-foreground">{it.hint}</span> : null}
                  </label>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {footer ? <div className="border-t border-border px-5 py-3">{footer}</div> : null}

      {showClear && value.length > 0 ? (
        <div className="border-t border-border px-5 py-2">
          <button
            type="button"
            onClick={() => onChange([])}
            className="min-h-11 text-sm font-medium text-muted-foreground hover:text-foreground hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
          >
            Clear
          </button>
        </div>
      ) : null}
    </>
  );
}

export function ChecklistPicker<V extends string | number = number>({
  items,
  value,
  onChange,
  title,
  emptyLabel = "None selected",
  searchPlaceholder = "Search",
  ariaLabel,
  footer,
  id,
  disabled = false,
  embedded = false,
  "aria-describedby": describedBy,
}: {
  items: ChecklistItem<V>[];
  value: V[];
  onChange: (next: V[]) => void;
  title: string;
  emptyLabel?: string;
  searchPlaceholder?: string;
  ariaLabel: string;
  footer?: ReactNode;
  id?: string;
  disabled?: boolean;
  /** Panel only — parent already provides a dialog (e.g. recording page). */
  embedded?: boolean;
  "aria-describedby"?: string;
}) {
  const [open, setOpen] = useState(false);
  const titleId = useId();

  const selectedItems = useMemo(
    () =>
      value
        .map((vid) => items.find((it) => it.value === vid))
        .filter((it): it is ChecklistItem<V> => Boolean(it)),
    [value, items],
  );

  const panel = (
    <ChecklistPickerPanel
      items={items}
      value={value}
      onChange={onChange}
      searchPlaceholder={searchPlaceholder}
      footer={footer}
      showClear
    />
  );

  if (embedded) {
    return <div className="flex min-h-0 flex-1 flex-col overflow-hidden">{panel}</div>;
  }

  return (
    <div>
      <button
        type="button"
        id={id}
        aria-label={ariaLabel}
        aria-describedby={describedBy}
        aria-haspopup="dialog"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => setOpen(true)}
        className={cn(
          FILTER_CONTROL,
          "flex h-auto min-h-[2.875rem] items-center gap-2 p-2 text-left font-medium disabled:cursor-not-allowed disabled:opacity-50",
        )}
      >
        <span className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
          {selectedItems.length === 0 ? (
            <span className="px-1 text-muted-foreground">{emptyLabel}</span>
          ) : (
            selectedItems.map((it) => (
              <span
                key={String(it.value)}
                className="inline-flex h-8 max-w-full items-center rounded-full border border-primary/20 bg-primary/5 px-3 text-sm font-medium text-primary"
              >
                <span className="truncate">{it.label}</span>
              </span>
            ))
          )}
        </span>
        <span className="inline-flex h-8 shrink-0 items-center rounded-lg bg-muted px-2.5 text-sm font-medium text-secondary-foreground">
          Select
        </span>
      </button>

      <Modal open={open} onClose={() => setOpen(false)} labelledBy={titleId} panelClassName="max-w-lg">
        <div className="flex h-[min(90vh,40rem)] flex-col overflow-hidden">
          <div className="flex items-center justify-between border-b border-border px-5 py-4">
            <div>
              <h2 id={titleId} className="text-sm font-semibold text-foreground">
                {title}
              </h2>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {value.length === 0 ? "None selected" : `${value.length} selected`}
              </p>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="Close dialog"
              tabIndex={-1}
              className="flex min-h-11 min-w-11 items-center justify-center text-muted-foreground hover:text-secondary-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
            >
              <X size={16} />
            </button>
          </div>
          {panel}
          <div className="flex justify-end border-t border-border px-5 py-3">
            <ActionButton size="sm" onClick={() => setOpen(false)}>
              Done
            </ActionButton>
          </div>
        </div>
      </Modal>
    </div>
  );
}
