"use client";

import { useCallback, useId, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { X, Link2, List, Upload, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/api/client";
import { NativeSelect } from "@/components/ui/native-select";
import { Modal } from "@/components/ui/modal";

type Tab = "url" | "playlist" | "file" | "sync";

// 5 GB hard cap on direct file uploads. Anything larger hits nginx
// client_max_body_size before the backend ever sees it — better to reject
// upfront with a clear message than to upload for an hour and see 413.
const MAX_UPLOAD_BYTES = 5 * 1024 * 1024 * 1024;

// Hosts the backend recognizes for URL/playlist ingestion (via yt-dlp). The
// check is a friendly client-side guard, not a security boundary — the backend
// still validates.
const SUPPORTED_VIDEO_HOSTS = [
  "youtube.com",
  "youtu.be",
  "vk.com",
  "vk.ru",
  "rutube.ru",
  "vimeo.com",
];

function isLikelySupportedUrl(raw: string): boolean {
  try {
    const u = new URL(raw);
    if (u.protocol !== "https:" && u.protocol !== "http:") return false;
    return SUPPORTED_VIDEO_HOSTS.some(
      (host) => u.hostname === host || u.hostname.endsWith(`.${host}`),
    );
  } catch {
    return false;
  }
}

function formatBytes(bytes: number): string {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(0)} MB`;
  return `${(bytes / 1024).toFixed(0)} KB`;
}

interface SourceItem {
  id: number;
  name: string;
  source_type: string;
  is_active: boolean;
}

interface SourceListResponse {
  items: SourceItem[];
  total: number;
}

interface AddVideoModalProps {
  open: boolean;
  onClose: () => void;
}

const QUALITY_OPTIONS = [
  { value: "best", label: "Best" },
  { value: "1080p", label: "1080p" },
  { value: "720p", label: "720p" },
  { value: "480p", label: "480p" },
];

const TABS = [
  { id: "url" as Tab, label: "URL", icon: Link2 },
  { id: "playlist" as Tab, label: "Playlist", icon: List },
  { id: "file" as Tab, label: "File", icon: Upload },
  { id: "sync" as Tab, label: "Source sync", icon: RefreshCw },
];

export function AddVideoModal({ open, onClose }: AddVideoModalProps) {
  const qc = useQueryClient();
  const titleId = useId();
  const [tab, setTab] = useState<Tab>("url");

  // URL / Playlist state
  const [url, setUrl] = useState("");
  const [quality, setQuality] = useState("best");
  const [autoRun, setAutoRun] = useState(false);

  // File state
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [fileDisplayName, setFileDisplayName] = useState("");

  // Source sync state
  const [selectedSources, setSelectedSources] = useState<Set<number>>(new Set());

  const [successMsg, setSuccessMsg] = useState("");
  const [errorMsg, setErrorMsg] = useState("");

  const handleClose = useCallback(() => {
    setSuccessMsg("");
    setErrorMsg("");
    onClose();
  }, [onClose]);

  const { data: sourcesData } = useQuery<SourceListResponse>({
    queryKey: ["sources-list"],
    queryFn: async () => {
      const res = await apiClient.get<SourceListResponse>("/sources");
      return res.data;
    },
    enabled: open && tab === "sync",
  });

  const addUrl = useMutation({
    mutationFn: (payload: { url: string; quality: string; auto_run: boolean }) =>
      apiClient.post("/recordings/add-url", payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["recordings"] });
      setSuccessMsg("Recording added!");
      setUrl("");
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setErrorMsg(msg ?? "Failed to add URL");
    },
  });

  const addPlaylist = useMutation({
    mutationFn: (payload: { url: string; quality: string; auto_run: boolean }) =>
      apiClient.post("/recordings/add-playlist", payload),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["recordings"] });
      const count = res.data?.recordings_created ?? 0;
      setSuccessMsg(`${count} recording${count !== 1 ? "s" : ""} added from playlist`);
      setUrl("");
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setErrorMsg(msg ?? "Failed to add playlist");
    },
  });

  const uploadFile = useMutation({
    mutationFn: ({ f, displayName }: { f: File; displayName: string }) => {
      const fd = new FormData();
      fd.append("file", f);
      // display_name is a required query param on POST /recordings
      const name = displayName.trim() || f.name.replace(/\.[^/.]+$/, "");
      return apiClient.post(`/recordings?display_name=${encodeURIComponent(name)}`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["recordings"] });
      setSuccessMsg("File uploaded!");
      setFile(null);
      setFileDisplayName("");
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setErrorMsg(msg ?? "Failed to upload file");
    },
  });

  const syncSource = useMutation({
    mutationFn: (sourceId: number) => apiClient.post(`/sources/${sourceId}/sync`),
    onSuccess: () => {
      setSuccessMsg("Sync started!");
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setErrorMsg(msg ?? "Sync failed");
    },
  });

  const isLoading = addUrl.isPending || addPlaylist.isPending || uploadFile.isPending || syncSource.isPending;

  function handleSubmit() {
    if (isLoading) return;
    setSuccessMsg("");
    setErrorMsg("");
    if (tab === "url" || tab === "playlist") {
      const trimmed = url.trim();
      if (!trimmed) { setErrorMsg(tab === "url" ? "Enter a URL" : "Enter a playlist URL"); return; }
      if (!isLikelySupportedUrl(trimmed)) {
        setErrorMsg(`Unsupported URL. Try: ${SUPPORTED_VIDEO_HOSTS.join(", ")}`);
        return;
      }
      const payload = { url: trimmed, quality, auto_run: autoRun };
      if (tab === "url") addUrl.mutate(payload);
      else addPlaylist.mutate(payload);
    } else if (tab === "file") {
      if (!file) { setErrorMsg("Select a file"); return; }
      if (file.size > MAX_UPLOAD_BYTES) {
        setErrorMsg(`File is too large (${formatBytes(file.size)}). Max allowed: ${formatBytes(MAX_UPLOAD_BYTES)}.`);
        return;
      }
      uploadFile.mutate({ f: file, displayName: fileDisplayName });
    } else if (tab === "sync") {
      if (selectedSources.size === 0) { setErrorMsg("Select at least one source"); return; }
      Array.from(selectedSources).forEach((id) => syncSource.mutate(id));
    }
  }

  const submitLabel =
    tab === "url" ? "Add video" :
    tab === "playlist" ? "Add playlist" :
    tab === "file" ? "Upload file" :
    "Start sync";

  return (
    <Modal open={open} onClose={handleClose} labelledBy={titleId} panelClassName="max-w-md overflow-hidden">
      <div className="bg-white">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[#D9D9D9]">
          <h2 id={titleId} className="text-base font-semibold text-gray-900">Add video</h2>
          <button
            type="button"
            onClick={handleClose}
            aria-label="Close dialog"
            className="p-1.5 rounded-lg hover:bg-gray-100 transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-[#D9D9D9]">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => { setTab(id); setSuccessMsg(""); setErrorMsg(""); }}
              className={cn(
                "flex items-center gap-1.5 flex-1 justify-center py-2.5 text-xs font-medium transition-colors border-b-2",
                tab === id
                  ? "border-[#224C87] text-[#224C87]"
                  : "border-transparent text-gray-500 hover:text-gray-700"
              )}
            >
              <Icon size={13} />
              {label}
            </button>
          ))}
        </div>

        {/* Body */}
        <div className="px-6 py-5 space-y-4">
          {(tab === "url" || tab === "playlist") && (
            <>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  {tab === "url" ? "Video URL" : "Playlist / channel URL"}
                </label>
                <input
                  type="url"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder={tab === "url" ? "https://youtube.com/watch?v=..." : "https://youtube.com/playlist?list=..."}
                  className="w-full px-4 py-2.5 rounded-xl border border-[#D9D9D9] text-sm outline-none focus:border-[#224C87] focus:ring-2 focus:ring-[#224C87]/10 transition-colors"
                />
              </div>
              <div className="flex gap-4">
                <div className="flex-1">
                  <label className="block text-sm font-medium text-gray-700 mb-1.5">Quality</label>
                  <NativeSelect
                    value={quality}
                    onChange={(e) => setQuality(e.target.value)}
                  >
                    {QUALITY_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </NativeSelect>
                </div>
                <div className="flex items-end pb-0.5">
                  <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={autoRun}
                      onChange={(e) => setAutoRun(e.target.checked)}
                      className="rounded accent-[#224C87]"
                    />
                    Auto-run
                  </label>
                </div>
              </div>
            </>
          )}

          {tab === "file" && (
            <div className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">Video file</label>
                <div
                  className={cn(
                    "border-2 border-dashed rounded-2xl p-8 text-center cursor-pointer transition-colors",
                    file ? "border-[#224C87] bg-[#224C87]/5" : "border-[#D9D9D9] hover:border-[#224C87]/50"
                  )}
                  onClick={() => fileRef.current?.click()}
                >
                  <Upload size={24} className="mx-auto mb-2 text-gray-400" />
                  {file ? (
                    <p className="text-sm font-medium text-[#224C87]">{file.name}</p>
                  ) : (
                    <p className="text-sm text-gray-500">Click to select a video file</p>
                  )}
                  <input
                    ref={fileRef}
                    type="file"
                    accept="video/*"
                    className="hidden"
                    onChange={(e) => {
                      const f = e.target.files?.[0] ?? null;
                      if (f && f.size > MAX_UPLOAD_BYTES) {
                        setErrorMsg(
                          `File is too large (${formatBytes(f.size)}). Max allowed: ${formatBytes(MAX_UPLOAD_BYTES)}.`,
                        );
                        setFile(null);
                        e.target.value = "";
                        return;
                      }
                      setErrorMsg("");
                      setFile(f);
                      if (f && !fileDisplayName) {
                        setFileDisplayName(f.name.replace(/\.[^/.]+$/, ""));
                      }
                    }}
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">Recording name</label>
                <input
                  type="text"
                  value={fileDisplayName}
                  onChange={(e) => setFileDisplayName(e.target.value)}
                  placeholder={file ? file.name.replace(/\.[^/.]+$/, "") : "Enter recording name"}
                  className="w-full px-4 py-2.5 rounded-xl border border-[#D9D9D9] text-sm outline-none focus:border-[#224C87] focus:ring-2 focus:ring-[#224C87]/10 transition-colors"
                />
              </div>
            </div>
          )}

          {tab === "sync" && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Select sources to sync</label>
              {!sourcesData?.items?.length ? (
                <p className="text-sm text-gray-400 py-4 text-center">
                  No sources configured. Add sources in the Sources section.
                </p>
              ) : (
                <div className="space-y-2 max-h-48 overflow-y-auto">
                  {sourcesData.items.filter((s) => s.is_active).map((s) => (
                    <label key={s.id} className="flex items-center gap-3 p-3 rounded-xl border border-[#D9D9D9] cursor-pointer hover:bg-gray-50 transition-colors">
                      <input
                        type="checkbox"
                        checked={selectedSources.has(s.id)}
                        onChange={() => {
                          setSelectedSources((prev) => {
                            const next = new Set(prev);
                            if (next.has(s.id)) next.delete(s.id);
                            else next.add(s.id);
                            return next;
                          });
                        }}
                        className="rounded accent-[#224C87]"
                      />
                      <span className="text-sm font-medium text-gray-900 flex-1">{s.name}</span>
                      <span className="text-xs text-gray-400">{s.source_type}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>
          )}

          {errorMsg && (
            <p className="text-sm text-red-500 bg-red-50 px-3 py-2 rounded-xl">{errorMsg}</p>
          )}
          {successMsg && (
            <p className="text-sm text-green-600 bg-green-50 px-3 py-2 rounded-xl">{successMsg}</p>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 pb-5 flex justify-end gap-3">
          <button
            onClick={handleClose}
            className="px-4 py-2.5 rounded-xl text-sm font-medium border border-[#D9D9D9] text-gray-600 hover:bg-gray-50 transition-colors"
          >
            Close
          </button>
          <button
            onClick={handleSubmit}
            disabled={isLoading}
            className="px-5 py-2.5 rounded-xl text-sm font-medium bg-[#224C87] text-white hover:bg-[#1a3d6e] disabled:opacity-50 transition-colors"
          >
            {isLoading ? "Loading…" : submitLabel}
          </button>
        </div>
      </div>
    </Modal>
  );
}
