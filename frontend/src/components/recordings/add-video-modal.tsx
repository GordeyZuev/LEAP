"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { X, Link2, List, Upload, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/api/client";

type Tab = "url" | "playlist" | "file" | "sync";

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
  const overlayRef = useRef<HTMLDivElement>(null);
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

  useEffect(() => {
    if (!open) return;
    setSuccessMsg("");
    setErrorMsg("");
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const isLoading = addUrl.isPending || addPlaylist.isPending || uploadFile.isPending || syncSource.isPending;

  function handleSubmit() {
    setSuccessMsg("");
    setErrorMsg("");
    if (tab === "url") {
      if (!url.trim()) { setErrorMsg("Enter a URL"); return; }
      addUrl.mutate({ url: url.trim(), quality, auto_run: autoRun });
    } else if (tab === "playlist") {
      if (!url.trim()) { setErrorMsg("Enter a playlist URL"); return; }
      addPlaylist.mutate({ url: url.trim(), quality, auto_run: autoRun });
    } else if (tab === "file") {
      if (!file) { setErrorMsg("Select a file"); return; }
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
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
      onClick={(e) => { if (e.target === overlayRef.current) onClose(); }}
    >
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md mx-4 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[#D9D9D9]">
          <h2 className="text-base font-semibold text-gray-900">Add video</h2>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 transition-colors">
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
                  <select
                    value={quality}
                    onChange={(e) => setQuality(e.target.value)}
                    className="w-full pl-3 pr-8 py-2.5 rounded-xl border border-[#D9D9D9] text-sm outline-none focus:border-[#224C87] focus:ring-2 focus:ring-[#224C87]/10 bg-white appearance-none"
                  >
                    {QUALITY_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
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
                            next.has(s.id) ? next.delete(s.id) : next.add(s.id);
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
            onClick={onClose}
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
    </div>
  );
}
