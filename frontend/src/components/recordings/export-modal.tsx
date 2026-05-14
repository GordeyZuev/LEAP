"use client";

import { useEffect, useState } from "react";
import { Download, Loader2, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/api/client";
import {
  FILTER_LABEL,
  FILTER_SEGMENT_ACTIVE,
  FILTER_SEGMENT_BTN,
  FILTER_SEGMENT_IDLE,
  FILTER_SEGMENT_WRAP,
} from "@/lib/filter-field-classes";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ExportFormat = "csv" | "xlsx" | "json";
type ExportVerbosity = "short" | "long";

export interface ExportModalProps {
  open: boolean;
  onClose: () => void;
  /** Selected recording IDs (if any) — used instead of filters when non-empty */
  selectedIds: number[];
  /** Raw URLSearchParams string of the currently applied filters */
  appliedFilterParams: string;
}

function parsePositiveIntParams(sp: URLSearchParams, key: string): number[] {
  return sp
    .getAll(key)
    .map((s) => parseInt(s, 10))
    .filter((n) => !Number.isNaN(n) && n > 0);
}

function buildFiltersFromParams(params: string): Record<string, unknown> {
  const sp = new URLSearchParams(params);
  const filters: Record<string, unknown> = {};

  const statuses = sp.getAll("status");
  if (statuses.length) filters.status = statuses;

  const templateIds = parsePositiveIntParams(sp, "template_id");
  if (templateIds.length) filters.template_ids = templateIds;

  const sourceIds = parsePositiveIntParams(sp, "source_id");
  if (sourceIds.length) filters.source_ids = sourceIds;

  const isMapped = sp.get("is_mapped");
  if (isMapped === "true") filters.is_mapped = true;
  else if (isMapped === "false") filters.is_mapped = false;

  if (sp.get("include_blank") !== "true") filters.exclude_blank = true;
  if (sp.get("include_deleted") === "true") filters.include_deleted = true;

  const fromDate = sp.get("from_date");
  if (fromDate) filters.from_date = fromDate;

  const toDate = sp.get("to_date");
  if (toDate) filters.to_date = toDate;

  const search = sp.get("search");
  if (search) filters.search = search;

  return filters;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ExportModal({
  open,
  onClose,
  selectedIds,
  appliedFilterParams,
}: ExportModalProps) {
  const [format, setFormat] = useState<ExportFormat>("xlsx");
  const [verbosity, setVerbosity] = useState<ExportVerbosity>("short");
  const [useSelected, setUseSelected] = useState(false);
  const [limit, setLimit] = useState("2000");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const hasSelected = selectedIds.length > 0;

  // When modal opens, default to selected if any
  useEffect(() => {
    if (open) {
      setUseSelected(selectedIds.length > 0);
      setError(null);
    }
  }, [open, selectedIds.length]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  async function handleExport() {
    setLoading(true);
    setError(null);

    const body: Record<string, unknown> = {
      format,
      verbosity,
    };

    if (useSelected && selectedIds.length > 0) {
      body.recording_ids = selectedIds;
    } else {
      const filters = buildFiltersFromParams(appliedFilterParams);
      if (Object.keys(filters).length > 0) body.filters = filters;
      const parsedLimit = parseInt(limit, 10);
      if (!Number.isNaN(parsedLimit) && parsedLimit > 0) body.limit = parsedLimit;
    }

    try {
      const res = await apiClient.post("/recordings/export", body, { responseType: "blob" });

      // Derive filename from Content-Disposition or fallback
      const cd = (res.headers as Record<string, string>)["content-disposition"] ?? "";
      const match = cd.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
      const filename =
        match?.[1]?.replace(/['"]/g, "") ??
        `recordings_export_${new Date().toISOString().slice(0, 10)}.${format}`;

      const blobUrl = URL.createObjectURL(res.data as Blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(blobUrl);

      onClose();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? "Export failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="w-full max-w-sm rounded-2xl bg-white shadow-xl mx-4">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[#EAEAEA] px-6 py-4">
          <h2 className="text-sm font-semibold text-gray-900">Export recordings</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 transition-colors">
            <X size={18} />
          </button>
        </div>

        <div className="space-y-5 p-6">
          {/* Scope */}
          {hasSelected && (
            <div className="space-y-1.5">
              <span className={FILTER_LABEL}>Scope</span>
              <div className={FILTER_SEGMENT_WRAP}>
                <button
                  type="button"
                  className={cn(FILTER_SEGMENT_BTN, useSelected ? FILTER_SEGMENT_ACTIVE : FILTER_SEGMENT_IDLE)}
                  onClick={() => setUseSelected(true)}
                >
                  {selectedIds.length} selected
                </button>
                <button
                  type="button"
                  className={cn(FILTER_SEGMENT_BTN, !useSelected ? FILTER_SEGMENT_ACTIVE : FILTER_SEGMENT_IDLE)}
                  onClick={() => setUseSelected(false)}
                >
                  All matching
                </button>
              </div>
            </div>
          )}

          {/* Limit (only when using filters) */}
          {(!hasSelected || !useSelected) && (
            <div className="space-y-1.5">
              <span className={FILTER_LABEL}>Max recordings</span>
              <input
                type="number"
                min={1}
                max={2000}
                value={limit}
                onChange={(e) => setLimit(e.target.value)}
                className="w-full min-h-[2.5rem] rounded-xl border border-[#D9D9D9] bg-white px-3 py-2 text-sm text-gray-900 outline-none transition-colors focus:border-[#224C87] focus:ring-2 focus:ring-[#224C87]/10"
              />
            </div>
          )}

          {/* Format */}
          <div className="space-y-1.5">
            <span className={FILTER_LABEL}>Format</span>
            <div className={FILTER_SEGMENT_WRAP}>
              {(["xlsx", "csv", "json"] as ExportFormat[]).map((f) => (
                <button
                  key={f}
                  type="button"
                  className={cn(
                    FILTER_SEGMENT_BTN,
                    format === f ? FILTER_SEGMENT_ACTIVE : FILTER_SEGMENT_IDLE
                  )}
                  onClick={() => setFormat(f)}
                >
                  {f.toUpperCase()}
                </button>
              ))}
            </div>
          </div>

          {/* Verbosity */}
          <div className="space-y-1.5">
            <span className={FILTER_LABEL}>Fields</span>
            <div className={FILTER_SEGMENT_WRAP}>
              {(["short", "long"] as ExportVerbosity[]).map((v) => (
                <button
                  key={v}
                  type="button"
                  className={cn(
                    FILTER_SEGMENT_BTN,
                    verbosity === v ? FILTER_SEGMENT_ACTIVE : FILTER_SEGMENT_IDLE
                  )}
                  onClick={() => setVerbosity(v)}
                >
                  {v === "short" ? "Short (core + URLs)" : "Long (full details)"}
                </button>
              ))}
            </div>
          </div>

          {error && (
            <p className="rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-xs text-red-600">
              {error}
            </p>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 border-t border-[#EAEAEA] px-6 py-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl border border-[#D9D9D9] px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleExport}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-xl bg-[#224C87] px-4 py-2 text-sm font-medium text-white hover:bg-[#1a3d6e] disabled:opacity-50 transition-colors"
          >
            {loading ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Download size={14} />
            )}
            Export
          </button>
        </div>
      </div>
    </div>
  );
}
