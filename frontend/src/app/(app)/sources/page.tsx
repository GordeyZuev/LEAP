"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, RefreshCw, Pencil, Trash2, X, Database } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/api/client";
import { Toast } from "@/components/ui/toast";
import { ActionButton } from "@/components/ui/action-button";
import { NativeSelect } from "@/components/ui/native-select";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { PageHeader } from "@/components/ui/page-header";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { CardGridSkeleton } from "@/components/ui/list-skeleton";
import { useToast } from "@/hooks/use-toast";
import { useDebounce } from "@/hooks/use-debounce";
import { FilterBar } from "@/components/filters/filter-bar";
import { SearchInput } from "@/components/filters/search-input";
import { SortControl } from "@/components/filters/sort-control";
import { FilterMultiSelect } from "@/components/filters/filter-multi-select";
import { DEBOUNCE_SEARCH, TOAST_SHORT } from "@/lib/constants";

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
];

type SortField = "name" | "last_sync_at";

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function sortSources(items: SourceItem[], sortBy: SortField, sortOrder: "asc" | "desc"): SourceItem[] {
  return [...items].sort((a, b) => {
    const cmp =
      sortBy === "name"
        ? a.name.localeCompare(b.name)
        : (a.last_sync_at ?? "").localeCompare(b.last_sync_at ?? "");
    return sortOrder === "asc" ? cmp : -cmp;
  });
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
  const [modalOpen, setModalOpen] = useState(false);
  const [editingSource, setEditingSource] = useState<SourceItem | null>(null);
  const [form, setForm] = useState<SourceForm>({ ...DEFAULT_FORM });
  const [formError, setFormError] = useState("");
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const { toast, show: showToast, dismiss: dismissToast } = useToast(TOAST_SHORT);

  // Filters (client-side — this list isn't paginated)
  const [searchInput, setSearchInput] = useState("");
  const [typeFilter, setTypeFilter] = useState<string[]>([]);
  const [sortBy, setSortBy] = useState<SortField>("name");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("asc");
  const debouncedSearch = useDebounce(searchInput, DEBOUNCE_SEARCH);

  const { data, isLoading, error, refetch } = useQuery<SourceListResponse>({
    queryKey: ["sources"],
    queryFn: async () => {
      const res = await apiClient.get<SourceListResponse>("/sources?per_page=50");
      return res.data;
    },
  });

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
    mutationFn: () =>
      apiClient.post("/sources/bulk/sync", { source_ids: sources.filter((s) => s.is_active).map((s) => s.id) }),
    onSuccess: () => showToast("success", "Sync started for all active sources"),
  });

  const deleteSource = useMutation({
    mutationFn: (id: number) => apiClient.delete(`/sources/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sources"] });
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
    setFormError("");
    saveSource.mutate(buildSourceBody(form));
  }

  const credsByPlatform = (credsData?.items ?? []).filter((c) => {
    if (form.platform === "ZOOM") return c.platform === "zoom";
    if (form.platform === "YANDEX_DISK") return c.platform === "yandex_disk";
    return false;
  });

  // React Compiler memoizes these plain derivations automatically.
  const sources = data?.items ?? [];
  const typeOptions = [...new Set(sources.map((s) => s.source_type))].map((t) => ({
    value: t,
    label: SOURCE_TYPE_LABELS[t] ?? t,
  }));
  const hasActiveFilters = !!debouncedSearch || typeFilter.length > 0 || sortBy !== "name" || sortOrder !== "asc";
  function resetFilters() {
    setSearchInput("");
    setTypeFilter([]);
    setSortBy("name");
    setSortOrder("asc");
  }
  const visibleSources = sortSources(
    sources.filter((s) => {
      if (debouncedSearch) {
        const q = debouncedSearch.toLowerCase();
        if (!s.name.toLowerCase().includes(q) && !(s.description ?? "").toLowerCase().includes(q)) return false;
      }
      if (typeFilter.length > 0 && !typeFilter.includes(s.source_type)) return false;
      return true;
    }),
    sortBy,
    sortOrder,
  );

  return (
    <div className="w-full min-w-0 p-6 sm:p-8">
      <PageHeader
        title="Input Sources"
        actions={
          <>
            {sources.length > 0 && (
              <ActionButton
                variant="secondary"
                isPending={bulkSync.isPending}
                disabled={sources.filter((s) => s.is_active).length === 0}
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
      {sources.length > 0 && (
        <FilterBar
          search={
            <SearchInput
              id="sources-search"
              value={searchInput}
              onChange={setSearchInput}
              placeholder="By name or description…"
            />
          }
          controls={[
            <FilterMultiSelect<string>
              key="type"
              label="Type"
              emptySummary="All types"
              value={typeFilter}
              options={typeOptions}
              onChange={setTypeFilter}
            />,
          ]}
          sort={
            <SortControl
              value={sortBy}
              order={sortOrder}
              options={SORT_OPTIONS}
              onChange={(f) => setSortBy(f as SortField)}
              onToggleOrder={() => setSortOrder((o) => (o === "desc" ? "asc" : "desc"))}
            />
          }
          onClearAll={hasActiveFilters ? resetFilters : undefined}
        />
      )}

      {isLoading && <CardGridSkeleton count={3} />}
      {error && <ErrorState description="Failed to load sources" onRetry={() => refetch()} />}
      {!isLoading && !error && sources.length === 0 && (
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
      )}
      {!isLoading && !error && sources.length > 0 && visibleSources.length === 0 && (
        <EmptyState icon={Database} title="No sources match your filters" description="Try adjusting or clearing the filters above." />
      )}

      {!isLoading && !error && visibleSources.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {visibleSources.map((s) => (
            <div key={s.id} className="bg-card rounded-2xl border border-border shadow-sm p-5 flex flex-col gap-3">
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
                  className="ml-auto border-red-200 text-red-500 hover:bg-red-50 dark:bg-red-500/10"
                />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add/Edit modal */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="bg-card rounded-2xl shadow-xl w-full max-w-md mx-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between px-6 py-4 border-b border-border sticky top-0 bg-card">
              <h2 className="text-base font-semibold text-foreground">{editingSource ? "Edit source" : "Add source"}</h2>
              <button onClick={() => setModalOpen(false)} className="p-1.5 rounded-lg hover:bg-muted"><X size={16} /></button>
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
                  {form.yd_use_public ? (
                    <MF label="Public URL"><input type="url" value={form.yd_public_url} onChange={(e) => setForm((f) => ({ ...f, yd_public_url: e.target.value }))} placeholder="https://disk.yandex.ru/d/..." className={inp} /></MF>
                  ) : (
                    <MF label="Folder path"><input type="text" value={form.yd_folder_path} onChange={(e) => setForm((f) => ({ ...f, yd_folder_path: e.target.value }))} placeholder="/Video/Lectures" className={inp} /></MF>
                  )}
                  <Toggle label="Recursive scan" checked={form.yd_recursive} onChange={(v) => setForm((f) => ({ ...f, yd_recursive: v }))} />
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
        </div>
      )}

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

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center justify-between py-2 cursor-pointer">
      <span className="text-sm font-medium text-secondary-foreground">{label}</span>
      <button type="button" onClick={() => onChange(!checked)} className={cn("relative inline-flex h-6 w-11 items-center rounded-full transition-colors", checked ? "bg-primary" : "bg-muted")}>
        <span className={cn("inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform", checked ? "translate-x-6" : "translate-x-1")} />
      </button>
    </label>
  );
}
