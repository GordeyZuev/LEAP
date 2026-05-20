"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, RefreshCw, Pencil, Trash2, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/api/client";
import { Toast } from "@/components/ui/toast";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useToast } from "@/hooks/use-toast";
import { TOAST_SHORT } from "@/lib/constants";

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
  ZOOM:        "bg-blue-100 text-blue-700",
  YANDEX_DISK: "bg-yellow-100 text-yellow-700",
  VIDEO_URL:   "bg-purple-100 text-purple-700",
};

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

  const { data, isLoading, error } = useQuery<SourceListResponse>({
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

  const sources = data?.items ?? [];

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6 gap-3">
        <h1 className="text-xl font-semibold text-gray-900">Input Sources</h1>
        <div className="flex items-center gap-2">
          {sources.length > 0 && (
            <button
              onClick={() => bulkSync.mutate()}
              disabled={bulkSync.isPending || sources.filter((s) => s.is_active).length === 0}
              className="flex items-center gap-2 rounded-xl border border-[#D9D9D9] bg-white px-4 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50 disabled:opacity-50"
            >
              <RefreshCw size={14} className={cn(bulkSync.isPending && "animate-spin")} />
              {bulkSync.isPending ? "Syncing…" : "Sync all"}
            </button>
          )}
          <button
            onClick={openCreate}
            className="flex items-center gap-2 bg-[#224C87] text-white px-4 py-2 rounded-xl text-sm font-medium hover:bg-[#1a3d6e] transition-colors"
          >
            <Plus size={16} /> Add source
          </button>
        </div>
      </div>

      {isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => <div key={i} className="bg-white rounded-2xl border border-[#D9D9D9] h-32 animate-pulse" />)}
        </div>
      )}
      {error && <p className="text-sm text-red-400">Failed to load sources</p>}
      {!isLoading && !error && sources.length === 0 && (
        <p className="text-sm text-gray-400 py-12 text-center">No sources yet</p>
      )}

      {!isLoading && !error && sources.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {sources.map((s) => (
            <div key={s.id} className="bg-white rounded-2xl border border-[#D9D9D9] shadow-sm p-5 flex flex-col gap-3">
              <div className="flex items-start justify-between gap-2">
                <span className="text-sm font-semibold text-gray-900 flex-1">{s.name}</span>
                <span className={cn("inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium shrink-0", SOURCE_TYPE_COLORS[s.source_type] ?? "bg-gray-100 text-gray-500")}>
                  {SOURCE_TYPE_LABELS[s.source_type] ?? s.source_type}
                </span>
              </div>
              {s.description && <p className="text-xs text-gray-400 line-clamp-2">{s.description}</p>}
              <p className="text-xs text-gray-400">
                {s.last_sync_at ? `Last sync: ${formatDate(s.last_sync_at)}` : "Never synced"}
              </p>
              <div className="flex items-center gap-2 mt-auto pt-2 border-t border-[#D9D9D9]">
                <button
                  onClick={() => syncSource.mutate(s.id)}
                  disabled={syncSource.isPending}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium border border-[#D9D9D9] bg-white hover:bg-[#224C87] hover:text-white hover:border-[#224C87] disabled:opacity-40 transition-colors"
                >
                  <RefreshCw size={12} /> Sync
                </button>
                <button
                  onClick={() => openEdit(s)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium border border-[#D9D9D9] bg-white hover:bg-gray-50 transition-colors"
                >
                  <Pencil size={12} /> Edit
                </button>
                <button
                  onClick={() => setDeleteId(s.id)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium border border-red-200 text-red-500 bg-white hover:bg-red-50 transition-colors ml-auto"
                >
                  <Trash2 size={12} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add/Edit modal */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md mx-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between px-6 py-4 border-b border-[#D9D9D9] sticky top-0 bg-white">
              <h2 className="text-base font-semibold text-gray-900">{editingSource ? "Edit source" : "Add source"}</h2>
              <button onClick={() => setModalOpen(false)} className="p-1.5 rounded-lg hover:bg-gray-100"><X size={16} /></button>
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
                          form.platform === t ? "bg-[#224C87] text-white border-[#224C87]" : "bg-white text-gray-600 border-[#D9D9D9] hover:bg-gray-50"
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
                    <p className="text-sm text-gray-400">No matching credentials. <a href="/credentials" className="text-[#224C87] hover:underline">Add credentials →</a></p>
                  ) : (
                    <select value={form.credential_id} onChange={(e) => setForm((f) => ({ ...f, credential_id: Number(e.target.value) || "" }))} className={cn(inp, "bg-white appearance-none pr-8")}>
                      <option value="">— Select —</option>
                      {credsByPlatform.map((c) => <option key={c.id} value={c.id}>{c.account_name ?? `Credential #${c.id}`}</option>)}
                    </select>
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
                    <select value={form.url_quality} onChange={(e) => setForm((f) => ({ ...f, url_quality: e.target.value }))} className={cn(inp, "bg-white appearance-none pr-8")}>
                      {["best", "1080p", "720p", "480p"].map((q) => <option key={q} value={q}>{q}</option>)}
                    </select>
                  </MF>
                </>
              )}

              {formError && <p className="text-sm text-red-500 bg-red-50 px-3 py-2 rounded-xl">{formError}</p>}
            </div>
            <div className="px-6 pb-5 flex justify-end gap-3">
              <button onClick={() => setModalOpen(false)} className="px-4 py-2.5 rounded-xl text-sm font-medium border border-[#D9D9D9] text-gray-600 hover:bg-gray-50">Cancel</button>
              <button onClick={handleSubmit} disabled={saveSource.isPending} className="px-5 py-2.5 rounded-xl text-sm font-medium bg-[#224C87] text-white hover:bg-[#1a3d6e] disabled:opacity-50 transition-colors">
                {saveSource.isPending ? "Saving…" : "Save"}
              </button>
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

const inp = "w-full px-4 py-2.5 rounded-xl border border-[#D9D9D9] text-sm outline-none focus:border-[#224C87] focus:ring-2 focus:ring-[#224C87]/10 transition-colors";

function MF({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1.5">{label}</label>
      {hint && <p className="text-xs text-gray-400 mb-1.5">{hint}</p>}
      {children}
    </div>
  );
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center justify-between py-2 cursor-pointer">
      <span className="text-sm font-medium text-gray-700">{label}</span>
      <button type="button" onClick={() => onChange(!checked)} className={cn("relative inline-flex h-6 w-11 items-center rounded-full transition-colors", checked ? "bg-[#224C87]" : "bg-gray-200")}>
        <span className={cn("inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform", checked ? "translate-x-6" : "translate-x-1")} />
      </button>
    </label>
  );
}
