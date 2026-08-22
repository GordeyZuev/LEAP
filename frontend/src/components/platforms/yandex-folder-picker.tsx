"use client";

import { useId, useMemo, useState } from "react";
import { keepPreviousData, useInfiniteQuery } from "@tanstack/react-query";
import { ChevronRight, Folder, Loader2, Search, X } from "lucide-react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { apiClient } from "@/api/client";
import { FILTER_CONTROL, FILTER_LABEL } from "@/lib/filter-field-classes";
import { ActionButton } from "@/components/ui/action-button";
import { Modal } from "@/components/ui/modal";

interface YandexDiskBrowseItem {
  name: string;
  path: string;
  type: "dir" | "file";
  size: number | null;
  mime_type: string | null;
}

interface YandexDiskBrowseResponse {
  path: string;
  items: YandexDiskBrowseItem[];
  total: number;
  offset: number;
  limit: number;
}

export interface YandexFolderPickerProps {
  value: string;
  onChange: (path: string) => void;
  credentialId: number | "";
  label?: string;
  placeholder?: string;
  /** "path" replaces value; "insert" appends chosen folder to template string */
  mode?: "path" | "insert";
  disabled?: boolean;
  /** Show only a Browse button (for use beside TemplateField). */
  compact?: boolean;
}

function buildBreadcrumbs(path: string): { label: string; path: string }[] {
  if (path === "/") return [{ label: "Root", path: "/" }];
  const parts = path.split("/").filter(Boolean);
  const crumbs: { label: string; path: string }[] = [{ label: "Root", path: "/" }];
  let acc = "";
  for (const part of parts) {
    acc += `/${part}`;
    crumbs.push({ label: part, path: acc });
  }
  return crumbs;
}

function applyInsertMode(current: string, folderPath: string): string {
  const base = folderPath.replace(/\/+$/, "") || "/";
  const trimmed = current.trim();
  if (!trimmed) return base === "/" ? "/" : base;
  if (trimmed.endsWith("/")) return `${trimmed.replace(/\/+$/, "")}${base === "/" ? "" : base}`;
  return `${trimmed.replace(/\/+$/, "")}${base === "/" ? "/" : base}`;
}

export function YandexFolderPicker({
  value,
  onChange,
  credentialId,
  label = "Folder path",
  placeholder = "No folder selected",
  mode = "path",
  disabled = false,
  compact = false,
}: YandexFolderPickerProps) {
  const [open, setOpen] = useState(false);
  const [browsePath, setBrowsePath] = useState("/");
  const [search, setSearch] = useState("");
  const titleId = useId();
  const searchId = useId();
  const limit = 100;

  const hasCredential = typeof credentialId === "number" && credentialId > 0;

  const { data, isLoading, isFetching, isFetchingNextPage, error, refetch, fetchNextPage, hasNextPage } =
    useInfiniteQuery<YandexDiskBrowseResponse>({
      queryKey: ["yandex-disk-browse", credentialId, browsePath],
      queryFn: async ({ pageParam }) => {
        const offset = pageParam as number;
        const params = new URLSearchParams({
          path: browsePath,
          limit: String(limit),
          offset: String(offset),
        });
        const res = await apiClient.get<YandexDiskBrowseResponse>(
          `/credentials/${credentialId}/yandex-disk/browse?${params.toString()}`
        );
        return res.data;
      },
      initialPageParam: 0,
      getNextPageParam: (lastPage) => {
        const nextOffset = lastPage.offset + lastPage.items.length;
        return nextOffset < lastPage.total ? nextOffset : undefined;
      },
      enabled: open && hasCredential,
      staleTime: 0,
      placeholderData: keepPreviousData,
    });

  const accumulatedItems = useMemo(
    () => data?.pages.flatMap((page) => page.items) ?? [],
    [data],
  );

  const folders = useMemo(
    () => accumulatedItems.filter((item) => item.type === "dir"),
    [accumulatedItems],
  );

  const filteredFolders = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return folders;
    return folders.filter((f) => f.name.toLowerCase().includes(q));
  }, [folders, search]);

  const hasMore = hasNextPage ?? false;
  const errDetail =
    (error as { response?: { data?: { detail?: string }; status?: number } } | null)?.response?.data?.detail;
  const errStatus =
    (error as { response?: { status?: number } } | null)?.response?.status;

  const hasListContent = folders.length > 0;
  const isInitialLoad = isLoading && !hasListContent;
  const isRefreshing = isFetching && !isFetchingNextPage && hasListContent;

  function handleOpen() {
    setBrowsePath("/");
    setSearch("");
    setOpen(true);
  }

  function navigateToPath(path: string) {
    if (isFetching) return;
    setBrowsePath(path);
    setSearch("");
  }

  function handleSelectFolder(path: string) {
    if (mode === "insert") {
      onChange(applyInsertMode(value, path));
    } else {
      onChange(path);
    }
    setOpen(false);
  }

  function openFolder(item: YandexDiskBrowseItem) {
    navigateToPath(item.path);
  }

  const triggerDisabled = disabled || !hasCredential;

  const browseButton = (
    <ActionButton
      size="sm"
      variant="secondary"
      disabled={triggerDisabled}
      onClick={handleOpen}
    >
      Browse…
    </ActionButton>
  );

  const emptyMessage = search.trim()
    ? "No folders match your filter."
    : "This folder has no subfolders.";

  return (
    <div className={compact ? undefined : "space-y-1"}>
      {!compact && label && <span className={FILTER_LABEL}>{label}</span>}
      {!compact && (
        <div className="flex items-center gap-2">
          <div className={cn(FILTER_CONTROL, "flex flex-1 items-center gap-2 py-1.5")}>
            <Folder size={14} className="shrink-0 text-muted-foreground" />
            <span className={cn("flex-1 truncate text-sm", value ? "text-foreground" : "text-muted-foreground")}>
              {value || placeholder}
            </span>
            {value && !disabled && (
              <button
                type="button"
                onClick={() => onChange("")}
                className="shrink-0 text-muted-foreground transition-colors duration-150 hover:text-secondary-foreground"
                aria-label="Clear folder path"
              >
                <X size={14} />
              </button>
            )}
          </div>
          {browseButton}
        </div>
      )}
      {compact && browseButton}
      {!compact && !hasCredential && !disabled && (
        <p className="text-xs text-muted-foreground">
          Select a Yandex Disk credential first, or{" "}
          <Link href="/credentials" className="text-primary hover:underline">
            connect one
          </Link>
          .
        </p>
      )}

      <Modal open={open} onClose={() => setOpen(false)} labelledBy={titleId} panelClassName="max-w-lg">
        <div className="flex max-h-[min(85vh,640px)] flex-col">
          <div className="flex shrink-0 items-center justify-between border-b border-border px-5 py-4">
            <h2 id={titleId} className="text-sm font-semibold text-foreground">
              Choose folder
            </h2>
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="Close dialog"
              className="text-muted-foreground transition-colors duration-150 hover:text-secondary-foreground"
            >
              <X size={16} />
            </button>
          </div>

          <div className="shrink-0 border-b border-border px-5 py-2.5">
            <nav aria-label="Folder path" className="flex flex-wrap items-center gap-0.5 text-xs">
              {buildBreadcrumbs(browsePath).map((crumb, idx, arr) => (
                <span key={crumb.path} className="flex items-center gap-0.5">
                  <button
                    type="button"
                    className={cn(
                      "max-w-[10rem] truncate rounded-md px-1.5 py-0.5 transition-colors duration-150",
                      idx === arr.length - 1
                        ? "font-medium text-foreground"
                        : "text-primary hover:bg-muted",
                    )}
                    onClick={() => navigateToPath(crumb.path)}
                    disabled={idx === arr.length - 1 || isFetching}
                    title={crumb.label}
                  >
                    {crumb.label}
                  </button>
                  {idx < arr.length - 1 && <ChevronRight size={12} className="shrink-0 text-muted-foreground" />}
                </span>
              ))}
            </nav>
          </div>

          {/* Fixed slot — search never mounts/unmounts while the dialog is open. */}
          <div className="shrink-0 border-b border-border px-5 py-2.5">
            <label htmlFor={searchId} className="sr-only">
              Filter folders
            </label>
            <div className="relative">
              <Search
                size={14}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
              />
              <input
                id={searchId}
                type="search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Filter folders…"
                disabled={!!error}
                className={cn(FILTER_CONTROL, "w-full py-2 pl-9 pr-3 text-sm transition-colors duration-150")}
              />
            </div>
          </div>

          <div className="relative min-h-[16rem] flex-1">
            <div
              className={cn(
                "h-full max-h-[min(24rem,45vh)] overflow-y-auto px-3 py-2 transition-opacity duration-150",
                isRefreshing && "pointer-events-none opacity-60",
              )}
              aria-busy={isFetching}
            >
              {error && (
                <div className="animate-fade-in space-y-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-400">
                  <p>{typeof errDetail === "string" ? errDetail : "Failed to load folder"}</p>
                  {errStatus === 401 && (
                    <Link href="/credentials" className="text-primary underline">
                      Re-authenticate Yandex Disk
                    </Link>
                  )}
                  <ActionButton size="sm" variant="secondary" onClick={() => refetch()}>
                    Retry
                  </ActionButton>
                </div>
              )}

              {!error && !isInitialLoad && filteredFolders.length === 0 && (
                <div className="flex h-full min-h-[14rem] items-center justify-center px-4">
                  <p className="animate-fade-in text-center text-sm text-muted-foreground">{emptyMessage}</p>
                </div>
              )}

              {!error && filteredFolders.length > 0 && (
                <ul
                  className="animate-fade-in divide-y divide-border overflow-hidden rounded-xl border border-border"
                  role="list"
                >
                  {filteredFolders.map((item) => (
                    <li key={item.path}>
                      <button
                        type="button"
                        className="flex w-full items-center gap-3 px-3 py-2.5 text-left text-sm transition-colors duration-150 hover:bg-muted"
                        onClick={() => openFolder(item)}
                        disabled={isFetching}
                      >
                        <Folder size={16} className="shrink-0 text-muted-foreground" strokeWidth={2} />
                        <span className="min-w-0 flex-1 truncate font-medium">{item.name}</span>
                        <ChevronRight size={14} className="shrink-0 text-muted-foreground" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              {!error && hasMore && (
                <div className="mt-3 flex justify-center pb-1">
                  <ActionButton
                    size="sm"
                    variant="secondary"
                    isPending={isFetchingNextPage}
                    onClick={() => fetchNextPage()}
                  >
                    Load more
                  </ActionButton>
                </div>
              )}
            </div>

            {(isInitialLoad || isRefreshing) && !error && (
              <div
                className="pointer-events-none absolute inset-0 flex items-center justify-center bg-card/50 backdrop-blur-[1px] transition-opacity duration-150"
                aria-hidden="true"
              >
                <Loader2 size={20} className="animate-spin text-muted-foreground" />
              </div>
            )}
          </div>

          <div className="flex shrink-0 items-center justify-between gap-3 border-t border-border px-5 py-4">
            <p className="truncate text-xs text-muted-foreground" title={browsePath}>
              {browsePath === "/" ? "Disk root" : browsePath}
            </p>
            <div className="flex shrink-0 gap-2">
              <ActionButton variant="secondary" onClick={() => setOpen(false)}>
                Cancel
              </ActionButton>
              <ActionButton
                onClick={() => handleSelectFolder(browsePath)}
                disabled={!!error || isInitialLoad}
              >
                Select folder
              </ActionButton>
            </div>
          </div>
        </div>
      </Modal>
    </div>
  );
}
