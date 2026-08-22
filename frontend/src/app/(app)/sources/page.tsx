"use client";

import { useId, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, RefreshCw, Pencil, Trash2, X, Database } from "lucide-react";
import { cn, extractApiError } from "@/lib/utils";
import { apiClient } from "@/api/client";
import { Toast } from "@/components/ui/toast";
import { ActionButton } from "@/components/ui/action-button";
import { NativeSelect } from "@/components/ui/native-select";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Modal } from "@/components/ui/modal";
import { Toggle } from "@/components/ui/toggle";
import { PageHeader } from "@/components/ui/page-header";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { CardGridSkeleton } from "@/components/ui/list-skeleton";
import { useToast } from "@/hooks/use-toast";
import { useUrlListState } from "@/hooks/use-url-list-state";
import { FilterBar } from "@/components/filters/filter-bar";
import { SearchInput } from "@/components/filters/search-input";
import { SortControl } from "@/components/filters/sort-control";
import { FilterMultiSelect } from "@/components/filters/filter-multi-select";
import { FilterChips, type FilterChipItem } from "@/components/filters/filter-chips";
import { Pagination } from "@/components/ui/pagination";
import { ResultCount } from "@/components/ui/result-count";
import { YandexFolderPicker } from "@/components/platforms/yandex-folder-picker";
import { PER_PAGE_SOURCES, TOAST_SHORT } from "@/lib/constants";

type SourceType = "ZOOM" | "YANDEX_DISK" | "VIDEO_URL";

interface SourceItem {
  id: number;
  name: string;
  description: string | null;
  source_type: string;
  is_active: boolean;
  last_sync_at: string | null;
  credential_id: number | null;
  config: Record<string, unknown> | null;
}

interface SourceListResponse {
  items: SourceItem[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

interface CredentialItem {
  id: number;
  platform: string;
  account_name: string | null;
}

interface SourceForm {
  name: string;
  description: string;
  platform: SourceType;
  credential_id: number | "";
  // ZOOM config
  zoom_user_emails: string;
  zoom_is_master: boolean;
  // YANDEX_DISK config
  yd_folder_path: string;
  yd_public_url: string;
  yd_use_public: boolean;
  yd_recursive: boolean;
  yd_file_pattern: string;
  // VIDEO_URL config
  url_url: string;
  url_is_playlist: boolean;
  url_quality: string;
}

const DEFAULT_FORM: SourceForm = {
  name: "",
  description: "",
  platform: "ZOOM",
  credential_id: "",
  zoom_user_emails: "",
  zoom_is_master: false,
  yd_folder_path: "",
  yd_public_url: "",
  yd_use_public: false,
  yd_recursive: true,
  yd_file_pattern: "",
  url_url: "",
  url_is_playlist: false,
  url_quality: "best",
};

const SOURCE_TYPE_LABELS: Record<string, string> = {
  ZOOM:        "Zoom",
  YANDEX_DISK: "Yandex Disk",
  VIDEO_URL:   "Video URL",
  LOCAL:       "Local",
};

const SOURCE_TYPE_COLORS: Record<string, string> = {
  ZOOM:        "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300",
  YANDEX_DISK: "bg-yellow-100 text-yellow-700 dark:bg-yellow-500/15 dark:text-yellow-300",
  VIDEO_URL:   "bg-purple-100 text-purple-700 dark:bg-purple-500/15 dark:text-purple-300",
};

const SORT_OPTIONS = [
  { value: "name",         label: "Name" },
  { value: "last_sync_at", label: "Last sync" },
  { value: "created_at",   label: "Created" },
];

const SORT_ALLOWED = SORT_OPTIONS.map((o) => o.value);

/** Filter options come from the known types, not from the loaded page — with
 *  server-side paging the page no longer contains every type in use. */
const TYPE_OPTIONS = (["ZOOM", "YANDEX_DISK", "VIDEO_URL", "LOCAL"] as const).map((t) => ({
  value: t as string,
  label: SOURCE_TYPE_LABELS[t],
}));

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function buildSourceBody(form: SourceForm) {
  const body: Record<string, unknown> = {
    name: form.name,
    description: form.description || undefined,
    platform: form.platform,
    credential_id: form.credential_id || undefined,
  };

  if (form.platform === "ZOOM") {
    body.config = {
      is_master_account: form.zoom_is_master,
      user_emails: form.zoom_is_master && form.zoom_user_emails
        ? form.zoom_user_emails.split("\n").map((s) => s.trim()).filter(Boolean)
        : undefined,
    };
  } else if (form.platform === "YANDEX_DISK") {
    body.config = {
      folder_path: !form.yd_use_public ? (form.yd_folder_path || undefined) : undefined,
      public_url: form.yd_use_public ? (form.yd_public_url || undefined) : undefined,
      recursive: form.yd_recursive,
      file_pattern: form.yd_file_pattern.trim() || undefined,
    };
  } else if (form.platform === "VIDEO_URL") {
    body.config = {
      url: form.url_url,
      is_playlist: form.url_is_playlist,
      quality: form.url_quality,
    };
  }

  return body;
}

export default function SourcesPage() {
  const qc = useQueryClient();
  const sourceModalTitleId = useId();
  const [modalOpen, setModalOpen] = useState(false);
  const [editingSource, setEditingSource] = useState<SourceItem | null>(null);
  const [form, setForm] = useState<SourceForm>({ ...DEFAULT_FORM });
  const [formError, setFormError] = useState("");
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const { toast, show: showToast, dismiss: dismissToast } = useToast(TOAST_SHORT);

  // Filters live in the URL so a filtered view is shareable and survives reload.
  const list = useUrlListState({
    defaultSortBy: "name",
    defaultSortOrder: "asc",
    allowedSortFields: SORT_ALLOWED,
  });
  const typeFilter = list.getAllParams("platform");

  const { data, isLoading, error, refetch } = useQuery<SourceListResponse>({
    queryKey: ["sources", list.urlKey],
    queryFn: async () => {
      const p = new URLSearchParams();
      if (list.search) p.set("search", list.search);
      typeFilter.forEach((t) => p.append("platform", t));
      p.set("sort_by", list.sortBy);
      p.set("sort_order", list.sortOrder);
      p.set("page", String(list.page));
      p.set("per_page", String(PER_PAGE_SOURCES));
      const res = await apiClient.get<SourceListResponse>(`/sources?${p.toString()}`);
      return res.data;
    },
  });

  // "Sync all" must mean every active source, not just the visible page.
  const { data: activeSources } = useQuery<SourceListResponse>({
    queryKey: ["sources-active"],
    queryFn: async () =>
      (await apiClient.get<SourceListResponse>("/sources?active_only=true&per_page=100")).data,
  });
  const activeSourceIds = (activeSources?.items ?? []).map((s) => s.id);

  const { data: credsData } = useQuery<{ items: CredentialItem[] }>({
    queryKey: ["credentials-list"],
    queryFn: async () => {
      const res = await apiClient.get("/credentials?per_page=50");
      return res.data;
    },
  });

  const saveSource = useMutation({
    mutationFn: (body: Record<string, unknown>) => {
      if (editingSource) return apiClient.patch(`/sources/${editingSource.id}`, body);
      return apiClient.post("/sources", body);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sources"] });
      qc.invalidateQueries({ queryKey: ["sources-active"] });
      qc.invalidateQueries({ queryKey: ["sources-list"] });
      setModalOpen(false);
      setEditingSource(null);
      setFormError("");
      showToast("success", "Source saved");
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setFormError(typeof msg === "string" ? msg : "Failed to save source");
    },
  });

  const syncSource = useMutation({
    mutationFn: (id: number) => apiClient.post(`/sources/${id}/sync`),
    onSuccess: () => showToast("success", "Sync started"),
  });

  const bulkSync = useMutation({
    mutationFn: () => apiClient.post("/sources/bulk/sync", { source_ids: activeSourceIds }),
    onSuccess: () => showToast("success", "Sync started for all active sources"),
    onError: (e) => showToast("error", extractApiError(e, "Failed to start sync")),
  });

  const deleteSource = useMutation({
    mutationFn: (id: number) => apiClient.delete(`/sources/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sources"] });
      qc.invalidateQueries({ queryKey: ["sources-active"] });
      qc.invalidateQueries({ queryKey: ["sources-list"] });
    },
  });

  function openCreate() {
    setForm({ ...DEFAULT_FORM });
    setEditingSource(null);
    setFormError("");
    setModalOpen(true);
  }

  function openEdit(s: SourceItem) {
    const cfg = s.config ?? {};
    setForm({
      name: s.name,
      description: s.description ?? "",
      platform: s.source_type as SourceType,
      credential_id: s.credential_id ?? "",
      zoom_user_emails: (cfg.user_emails as string[] | undefined)?.join("\n") ?? "",
      zoom_is_master: (cfg.is_master_account as boolean | undefined) ?? false,
      yd_folder_path: (cfg.folder_path as string | undefined) ?? "",
      yd_public_url: (cfg.public_url as string | undefined) ?? "",
      yd_use_public: !!(cfg.public_url),
      yd_recursive: (cfg.recursive as boolean | undefined) ?? true,
      yd_file_pattern: (cfg.file_pattern as string | undefined) ?? "",
      url_url: (cfg.url as string | undefined) ?? "",
      url_is_playlist: (cfg.is_playlist as boolean | undefined) ?? false,
      url_quality: (cfg.quality as string | undefined) ?? "best",
    });
    setEditingSource(s);
    setFormError("");
    setModalOpen(true);
  }

  function handleSubmit() {
    if (!form.name) { setFormError("Name is required"); return; }
    if (form.platform === "YANDEX_DISK") {
      if (form.yd_use_public) {
        if (!form.yd_public_url.trim()) {
          setFormError("Public URL is required");
          return;
        }
      } else {
        if (!form.credential_id) {
          setFormError("Credential is required for folder sync");
          return;
        }
        if (!form.yd_folder_path.trim()) {
          setFormError("Folder path is required");
          return;
        }
      }
    }
    setFormError("");
    saveSource.mutate(buildSourceBody(form));
  }

  const credsByPlatform = (credsData?.items ?? []).filter((c) => {
    if (form.platform === "ZOOM") return c.platform === "zoom";
    if (form.platform === "YANDEX_DISK") return c.platform === "yandex_disk";
    return false;
  });

  // Filtering, sorting and paging are done by the API — the page just renders.
  const sources = data?.items ?? [];
  const hasAnySource = (activeSources?.total ?? 0) > 0 || sources.length > 0 || list.hasActiveFilters;

  const chips: FilterChipItem[] = [
    ...(list.search
      ? [{
          key: "search",
          label: `Search: "${list.search}"`,
          onRemove: () => { list.setSearchInput(""); list.setParam("search", null); },
        }]
      : []),
    ...typeFilter.map((t) => ({
      key: `platform:${t}`,
      label: SOURCE_TYPE_LABELS[t] ?? t,
      onRemove: () => list.setMultiParam("platform", typeFilter.filter((x) => x !== t)),
    })),
  ];

  return (
    <div className="w-full min-w-0 p-6 sm:p-8">
      <PageHeader
        title="Input Sources"
        actions={
          <>
            {activeSourceIds.length > 0 && (
              <ActionButton
                variant="secondary"
                isPending={bulkSync.isPending}
                onClick={() => bulkSync.mutate()}
                icon={<RefreshCw size={14} />}
                pendingLabel="Syncing…"
              >
                Sync all
              </ActionButton>
            )}
            <ActionButton onClick={openCreate} icon={<Plus size={16} />}>
              Add source
            </ActionButton>
          </>
        }
      />

      {/* Filters — only meaningful once there are sources */}
      {hasAnySource && (
        <FilterBar
          search={
            <SearchInput
              id="sources-search"
              value={list.searchInput}
              onChange={list.setSearchInput}
              placeholder="By name or description…"
            />
          }
          controls={[
            <FilterMultiSelect<string>
              key="type"
              label="Type"
              emptySummary="All types"
              value={typeFilter}
              options={TYPE_OPTIONS}
              onChange={(next) => list.setMultiParam("platform", next)}
            />,
          ]}
          sort={
            <SortControl
              value={list.sortBy}
              order={list.sortOrder}
              options={SORT_OPTIONS}
              onChange={list.setSort}
              onToggleOrder={list.toggleSortOrder}
            />
          }
          onClearAll={list.hasActiveFilters || list.hasNonDefaultSort ? list.resetAll : undefined}
          chips={<FilterChips chips={chips} />}
        />
      )}

      <ResultCount total={data?.total} itemLabel="source" filtered={list.hasActiveFilters} />

      {isLoading && <CardGridSkeleton count={3} />}
      {error && <ErrorState description="Failed to load sources" onRetry={() => refetch()} />}
      {!isLoading && !error && sources.length === 0 && (
        list.hasActiveFilters ? (
          <EmptyState
            icon={Database}
            title="No sources match your filters"
            description="Try adjusting or clearing the filters above."
            action={
              <ActionButton variant="secondary" onClick={list.resetAll}>
                Reset filters
              </ActionButton>
            }
          />
        ) : (
          <EmptyState
            icon={Database}
            title="No sources yet"
            description="Sources pull recordings in automatically (Zoom, Yandex Disk, and more). Add one to start ingesting."
            action={
              <ActionButton onClick={openCreate} icon={<Plus size={16} />}>
                Add source
              </ActionButton>
            }
          />
        )
      )}

      {!isLoading && !error && sources.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {sources.map((s, index) => (
            <div key={s.id} className="bg-card rounded-2xl border border-border shadow-sm p-5 flex flex-col gap-3 animate-card-in" style={{ animationDelay: `${index * 30}ms` }}>
              <div className="flex items-start justify-between gap-2">
                <span className="text-sm font-semibold text-foreground flex-1">{s.name}</span>
                <span className={cn("inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium shrink-0", SOURCE_TYPE_COLORS[s.source_type] ?? "bg-muted text-muted-foreground")}>
                  {SOURCE_TYPE_LABELS[s.source_type] ?? s.source_type}
                </span>
              </div>
              {s.description && <p className="text-xs text-muted-foreground line-clamp-2">{s.description}</p>}
              <p className="text-xs text-muted-foreground">
                {s.last_sync_at ? `Last sync: ${formatDate(s.last_sync_at)}` : "Never synced"}
              </p>
              <div className="flex items-center gap-2 mt-auto pt-2 border-t border-border">
                <ActionButton
                  size="sm"
                  variant="secondary"
                  onClick={() => syncSource.mutate(s.id)}
                  isPending={syncSource.isPending && syncSource.variables === s.id}
                  icon={<RefreshCw size={12} />}
                  pendingLabel="Syncing…"
                  className="hover:border-primary hover:bg-primary hover:text-white"
                >
                  Sync
                </ActionButton>
                <ActionButton size="sm" variant="secondary" onClick={() => openEdit(s)} icon={<Pencil size={12} />}>
                  Edit
                </ActionButton>
                <ActionButton
                  size="sm"
                  variant="secondary"
                  onClick={() => setDeleteId(s.id)}
                  icon={<Trash2 size={12} />}
                  className="ml-auto border-red-200 text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10"
                />
              </div>
            </div>
          ))}
        </div>
      )}

      {data && (
        <Pagination
          page={list.page}
          totalPages={data.total_pages}
          total={data.total}
          perPage={PER_PAGE_SOURCES}
          onPageChange={list.setPage}
          itemLabel="source"
        />
      )}

      {/* Add/Edit modal */}
      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        labelledBy={sourceModalTitleId}
        panelClassName="max-w-md max-h-[90vh] overflow-y-auto"
      >
          <div>
            <div className="flex items-center justify-between px-6 py-4 border-b border-border sticky top-0 bg-card">
              <h2 id={sourceModalTitleId} className="text-base font-semibold text-foreground">{editingSource ? "Edit source" : "Add source"}</h2>
              <button type="button" onClick={() => setModalOpen(false)} aria-label="Close dialog" className="p-1.5 rounded-lg hover:bg-muted"><X size={16} /></button>
            </div>
            <div className="px-6 py-5 space-y-4">
              <MF label="Name *">
                <input type="text" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} placeholder="My Zoom source" className={inp} />
              </MF>
              <MF label="Description">
                <input type="text" value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} placeholder="Optional" className={inp} />
              </MF>

              {/* Type selector (only for new) */}
              {!editingSource && (
                <MF label="Type">
                  <div className="flex gap-2">
                    {(["ZOOM", "YANDEX_DISK", "VIDEO_URL"] as SourceType[]).map((t) => (
                      <button key={t} type="button"
                        onClick={() => setForm((f) => ({ ...f, platform: t, credential_id: "" }))}
                        className={cn("flex-1 py-2 rounded-xl text-xs font-medium border transition-colors",
                          form.platform === t ? "bg-primary text-white border-primary" : "bg-card text-secondary-foreground border-border hover:bg-muted"
                        )}
                      >
                        {SOURCE_TYPE_LABELS[t]}
                      </button>
                    ))}
                  </div>
                </MF>
              )}

              {/* Credential */}
              {form.platform !== "VIDEO_URL" && (
                <MF label="Credential">
                  {credsByPlatform.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No matching credentials. <a href="/credentials" className="text-primary hover:underline">Add credentials →</a></p>
                  ) : (
                    <NativeSelect value={form.credential_id} onChange={(e) => setForm((f) => ({ ...f, credential_id: Number(e.target.value) || "" }))}>
                      <option value="">— Select —</option>
                      {credsByPlatform.map((c) => <option key={c.id} value={c.id}>{c.account_name ?? `Credential #${c.id}`}</option>)}
                    </NativeSelect>
                  )}
                </MF>
              )}

              {/* ZOOM config */}
              {form.platform === "ZOOM" && (
                <>
                  <Toggle label="Master account (all users)" checked={form.zoom_is_master} onChange={(v) => setForm((f) => ({ ...f, zoom_is_master: v }))} />
                  {form.zoom_is_master && (
                    <MF label="User emails" hint="One per line">
                      <textarea value={form.zoom_user_emails} onChange={(e) => setForm((f) => ({ ...f, zoom_user_emails: e.target.value }))} rows={3} placeholder="user@example.com" className={cn(inp, "resize-none")} />
                    </MF>
                  )}
                </>
              )}

              {/* YANDEX_DISK config */}
              {form.platform === "YANDEX_DISK" && (
                <>
                  <Toggle label="Use public link" checked={form.yd_use_public} onChange={(v) => setForm((f) => ({ ...f, yd_use_public: v }))} />
                  <p className="text-xs text-muted-foreground -mt-2">
                    Public link: paste a share URL (no credential). Private folder: OAuth + browse your Disk tree.
                    Yandex 360 shared folders appear in browse after you accept the invite.
                  </p>
                  {form.yd_use_public ? (
                    <MF label="Public URL"><input type="url" value={form.yd_public_url} onChange={(e) => setForm((f) => ({ ...f, yd_public_url: e.target.value }))} placeholder="https://disk.yandex.ru/d/..." className={inp} /></MF>
                  ) : (
                    <YandexFolderPicker
                      value={form.yd_folder_path}
                      onChange={(p) => setForm((f) => ({ ...f, yd_folder_path: p }))}
                      credentialId={form.credential_id}
                      label="Folder path"
                      placeholder="/Video/Lectures"
                      mode="path"
                    />
                  )}
                  <Toggle label="Recursive scan" checked={form.yd_recursive} onChange={(v) => setForm((f) => ({ ...f, yd_recursive: v }))} />
                  <MF label="File pattern" hint="Optional regex, e.g. .*\.mp4$">
                    <input type="text" value={form.yd_file_pattern} onChange={(e) => setForm((f) => ({ ...f, yd_file_pattern: e.target.value }))} placeholder=".*\.mp4$" className={inp} />
                  </MF>
                </>
              )}

              {/* VIDEO_URL config */}
              {form.platform === "VIDEO_URL" && (
                <>
                  <MF label="URL *"><input type="url" value={form.url_url} onChange={(e) => setForm((f) => ({ ...f, url_url: e.target.value }))} placeholder="https://youtube.com/..." className={inp} /></MF>
                  <Toggle label="Playlist" checked={form.url_is_playlist} onChange={(v) => setForm((f) => ({ ...f, url_is_playlist: v }))} />
                  <MF label="Quality">
                    <NativeSelect value={form.url_quality} onChange={(e) => setForm((f) => ({ ...f, url_quality: e.target.value }))}>
                      {["best", "1080p", "720p", "480p"].map((q) => <option key={q} value={q}>{q}</option>)}
                    </NativeSelect>
                  </MF>
                </>
              )}

              {formError && <p className="text-sm text-red-500 bg-red-50 dark:bg-red-500/10 px-3 py-2 rounded-xl">{formError}</p>}
            </div>
            <div className="px-6 pb-5 flex justify-end gap-3">
              <ActionButton variant="secondary" onClick={() => setModalOpen(false)} className="py-2.5">Cancel</ActionButton>
              <ActionButton onClick={handleSubmit} isPending={saveSource.isPending} isSuccess={saveSource.isSuccess} pendingLabel="Saving…" className="px-5 py-2.5">
                Save
              </ActionButton>
            </div>
          </div>
      </Modal>

      <ConfirmDialog
        open={deleteId !== null}
        title="Delete source?"
        description="This source will be permanently deleted. Previously imported recordings won't be affected. Templates using this source in their matching rules will have it removed automatically."
        confirmLabel="Delete"
        cancelLabel="Cancel"
        danger
        onConfirm={() => { if (deleteId !== null) deleteSource.mutate(deleteId); setDeleteId(null); }}
        onCancel={() => setDeleteId(null)}
      />

      {toast && <Toast key={toast.serial} type={toast.type} message={toast.msg} exiting={toast.exiting} onDismiss={dismissToast} />}
    </div>
  );
}

const inp = "w-full px-4 py-2.5 rounded-xl border border-border text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/10 transition-colors";

function MF({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-sm font-medium text-secondary-foreground mb-1.5">{label}</label>
      {hint && <p className="text-xs text-muted-foreground mb-1.5">{hint}</p>}
      {children}
    </div>
  );
}
