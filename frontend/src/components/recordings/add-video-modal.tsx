"use client";

import Link from "next/link";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { X, Upload, ScanLine, Loader2 } from "lucide-react";
import { cn, collapseWhitespace, extractApiError, formatDurationCompact, httpStatus } from "@/lib/utils";
import { CHECKBOX, FILTER_CONTROL, FILTER_LABEL } from "@/lib/filter-field-classes";
import { apiClient } from "@/api/client";
import { NativeSelect } from "@/components/ui/native-select";
import { Modal } from "@/components/ui/modal";
import { ActionButton } from "@/components/ui/action-button";
import { ProgressBar } from "@/components/ui/progress-bar";
import { Field } from "@/components/ui/field";
import { Tabs, type TabItem } from "@/components/ui/tabs";
import { SegmentedField, type SegmentedOption } from "@/components/ui/segmented-field";

type LinkTab = "url" | "playlist" | "disk";
type DiskKind = "file" | "dir";
type TopTab = "sync" | "file" | "link";
type Tab = LinkTab | Exclude<TopTab, "link">;

// Fallback until the backend policy loads. nginx allows 5001 MiB for multipart overhead.
const DEFAULT_MAX_UPLOAD_BYTES = 5000 * 1024 * 1024;
const DEFAULT_VIDEO_EXTENSIONS = [".mp4", ".webm", ".mkv", ".mov"];

interface UploadPolicy {
  max_upload_bytes: number;
  extensions: string[];
  resume_hours: number;
}

interface ResumableUploadStatus {
  upload_id: string;
  offset: number;
  size: number;
  chunk_size: number;
  fingerprint: string;
  recording_id: number | null;
  display_name: string;
  auto_run: boolean;
}

async function fileFingerprint(file: File): Promise<string> {
  const sample = 64 * 1024;
  const bytes = await new Blob([
    `${file.name}:${file.size}:${file.lastModified}:`,
    file.slice(0, sample),
    file.slice(Math.max(0, file.size - sample)),
  ]).arrayBuffer();
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function savedUploadId(key: string): string | null {
  try { return window.localStorage.getItem(key); } catch { return null; }
}

function rememberUpload(key: string, id: string | null): void {
  try {
    if (id) window.localStorage.setItem(key, id);
    else window.localStorage.removeItem(key);
  } catch { /* Upload still works without browser storage. */ }
}

// Hosts the backend recognizes for URL/playlist ingestion (via yt-dlp). The
// check is a friendly client-side guard, not a security boundary — the backend
// still validates.
const SUPPORTED_VIDEO_HOSTS = [
  "youtube.com",
  "youtu.be",
  "youtube-nocookie.com",
  "vk.com",
  "vk.ru",
  "vkvideo.ru",
  "rutube.ru",
  "vimeo.com",
];
const DISK_HOSTS = ["disk.yandex.ru", "disk.yandex.com", "disk.yandex.net", "yadi.sk"];

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

function isLikelyYoutubePlaylistUrl(raw: string): boolean {
  try {
    const url = new URL(raw);
    return (url.protocol === "https:" || url.protocol === "http:")
      && (url.hostname === "youtube.com" || url.hostname.endsWith(".youtube.com"))
      && Boolean(url.searchParams.get("list"));
  } catch {
    return false;
  }
}

function isLikelyDiskUrl(raw: string): boolean {
  try {
    const url = new URL(raw);
    return url.protocol === "https:" && DISK_HOSTS.includes(url.hostname);
  } catch {
    return false;
  }
}

function formatBytes(bytes: number): string {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GiB`;
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(0)} MiB`;
  return `${(bytes / 1024).toFixed(0)} KiB`;
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

interface SyncTaskStatus {
  state: string;
  result: {
    status?: string;
    error?: string;
    recordings_saved?: number;
    recordings_updated?: number;
    pipelines_started?: number;
    failed?: number;
    successful?: number;
    results?: Array<{ recordings_saved?: number; recordings_updated?: number }>;
  } | null;
  error: string | null;
}

interface AddVideoModalProps {
  open: boolean;
  onClose: () => void;
}

interface FormatInfo {
  height: number | null;
  vcodec: string;
}

interface FormatsPreviewResponse {
  title: string;
  duration: number | null;
  thumbnail: string | null;
  platform: string;
  formats: FormatInfo[];
}

interface PlaylistPreviewResponse {
  video_count: number;
  unavailable_count: number;
  sample_titles: string[];
}

interface DiskPreviewResponse {
  resource_type: DiskKind;
  name: string;
  video_count: number;
  sample_names: string[];
}

const PREVIEW_DEBOUNCE_MS = 500;

const STATIC_QUALITY_OPTIONS = [
  { value: "best", label: "Best" },
  { value: "1080p", label: "1080p" },
  { value: "720p", label: "720p" },
  { value: "480p", label: "480p" },
];

const SOURCE_TYPE_LABELS: Record<string, string> = {
  ZOOM: "Zoom",
  MTS_LINK: "MTS Link",
  YANDEX_DISK: "Yandex Disk",
  VIDEO_URL: "Video link",
};

function buildFormatOptions(formats: FormatInfo[]): { value: string; label: string }[] {
  const heights = [...new Set(formats
    .filter((f) => f.vcodec !== "none" && typeof f.height === "number" && f.height >= 10 && f.height <= 4320)
    .map((f) => f.height as number))].sort((a, b) => b - a);
  return [STATIC_QUALITY_OPTIONS[0], ...heights.map((height) => ({
    value: `${height}p`, label: `${height}p`,
  }))];
}

function UrlLinkPreview({
  title,
  thumbnail,
  duration,
}: {
  title: string;
  thumbnail: string | null;
  duration: number | null;
}) {
  const [imgFailed, setImgFailed] = useState(false);
  const dur = formatDurationCompact(duration);
  const showImg = Boolean(thumbnail) && !imgFailed;

  return (
    <div className="mt-2 overflow-hidden rounded-xl border border-border bg-muted/30">
      {showImg ? (
        <div className="relative aspect-video bg-muted">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={thumbnail ?? ""}
            alt=""
            referrerPolicy="no-referrer"
            loading="lazy"
            decoding="async"
            onError={() => setImgFailed(true)}
            className="h-full w-full object-cover"
          />
          {dur ? (
            <span className="absolute bottom-1 end-1 rounded bg-black/70 px-1 py-0.5 text-xs font-medium tabular-nums text-white">
              {dur}
            </span>
          ) : null}
        </div>
      ) : null}
      <p className="px-3 py-2 text-sm font-medium text-foreground">
        {title}
      </p>
    </div>
  );
}

const TABS = [
  { value: "sync", label: "Sources" },
  { value: "file", label: "File" },
  { value: "link", label: "Link" },
] satisfies TabItem<TopTab>[];

const LINK_TYPES = [
  { value: "url", label: "Video" },
  { value: "playlist", label: "Playlist" },
  { value: "disk", label: "Disk" },
] satisfies SegmentedOption<LinkTab>[];

const DISK_TYPES = [
  { value: "file", label: "One video" },
  { value: "dir", label: "Folder" },
] satisfies SegmentedOption<DiskKind>[];

export function AddVideoModal({ open, onClose }: AddVideoModalProps) {
  const qc = useQueryClient();
  const invalidateRecordings = useCallback(() => {
    void qc.invalidateQueries({ queryKey: ["recordings"] });
    void qc.invalidateQueries({ queryKey: ["home"] });
  }, [qc]);
  const titleId = useId();
  const [topTab, setTopTab] = useState<TopTab>("sync");
  const [linkTab, setLinkTab] = useState<LinkTab>("url");
  const tab: Tab = topTab === "link" ? linkTab : topTab;

  // URL / Playlist state
  const [url, setUrl] = useState("");
  const [urlDisplayName, setUrlDisplayName] = useState<string | null>(null);
  const [quality, setQuality] = useState("best");
  const [autoRun, setAutoRun] = useState(false);
  const [debouncedUrl, setDebouncedUrl] = useState("");
  const [diskUrl, setDiskUrl] = useState("");
  const [debouncedDiskUrl, setDebouncedDiskUrl] = useState("");
  const [diskKind, setDiskKind] = useState<DiskKind>("file");
  const [diskSourceName, setDiskSourceName] = useState<string | null>(null);

  // File state
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [fileDisplayName, setFileDisplayName] = useState("");
  const [isDragging, setIsDragging] = useState(false);

  // Source sync state
  const [selectedSources, setSelectedSources] = useState<Set<number>>(new Set());
  const [sourceSearch, setSourceSearch] = useState("");

  const [successMsg, setSuccessMsg] = useState("");
  const [errorMsg, setErrorMsg] = useState("");
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [resumedFrom, setResumedFrom] = useState<number | null>(null);
  const [syncTaskId, setSyncTaskId] = useState<string | null>(null);

  const syncTask = useQuery<SyncTaskStatus>({
    queryKey: ["add-video-sync-task", syncTaskId],
    queryFn: async () => (await apiClient.get<SyncTaskStatus>(`/tasks/${syncTaskId}`)).data,
    enabled: !!syncTaskId,
    retry: false,
    refetchInterval: (query) =>
      query.state.status === "error" || ["SUCCESS", "FAILURE"].includes(query.state.data?.state ?? "")
        ? false : 2000,
  });

  useEffect(() => {
    const task = syncTask.data;
    if (syncTaskId && task?.state === "SUCCESS" && task.result?.status !== "error") {
      invalidateRecordings();
    }
  }, [invalidateRecordings, syncTask.data, syncTaskId]);

  const syncFeedbackVisible = tab === "sync" || tab === "disk";
  const syncInFlight = Boolean(
    syncTaskId && !syncTask.isError && syncTask.data?.state !== "SUCCESS" && syncTask.data?.state !== "FAILURE"
  );
  const syncTaskError = syncTask.isError
    ? "Could not check sync status. Check Sources for progress."
    : syncTask.data?.state === "FAILURE" || syncTask.data?.result?.status === "error"
      ? syncTask.data.error || syncTask.data.result?.error || "Sync failed. Check Sources and try again."
      : syncTask.data?.result?.failed && syncTask.data.result.successful === 0
        ? "All selected sources failed to sync. Check Sources for details."
      : "";
  const syncTaskResult = syncTask.data?.state === "SUCCESS" && !syncTaskError ? syncTask.data.result : null;
  const syncSaved = syncTaskResult?.recordings_saved ?? syncTaskResult?.results?.reduce((total, item) => total + (item.recordings_saved ?? 0), 0) ?? 0;
  const syncUpdated = syncTaskResult?.recordings_updated ?? syncTaskResult?.results?.reduce((total, item) => total + (item.recordings_updated ?? 0), 0) ?? 0;
  const syncTaskSummary = syncTaskResult
    ? `Sync complete: ${syncSaved} new, ${syncUpdated} already present${syncTaskResult.pipelines_started ? `, ${syncTaskResult.pipelines_started} processing started` : ""}${syncTaskResult.failed ? `, ${syncTaskResult.failed} sources failed` : ""}.`
    : "";
  const visibleError = syncFeedbackVisible ? syncTaskError || errorMsg : errorMsg;
  const visibleSuccess = syncFeedbackVisible && (syncTaskError || syncTaskSummary)
    ? syncTaskSummary : successMsg;

  const { data: uploadPolicy } = useQuery<UploadPolicy>({
    queryKey: ["recording-upload-policy"],
    queryFn: async () => (await apiClient.get<UploadPolicy>("/recordings/upload-policy")).data,
    enabled: open,
    staleTime: 5 * 60 * 1000,
  });
  const maxUploadBytes = uploadPolicy?.max_upload_bytes ?? DEFAULT_MAX_UPLOAD_BYTES;
  const videoExtensions = uploadPolicy?.extensions ?? DEFAULT_VIDEO_EXTENSIONS;

  // Shared accept path for click-select and drag & drop.
  const acceptFile = useCallback((f: File | null) => {
    if (!f) return;
    setFile(null);
    setFileDisplayName("");
    if (!videoExtensions.some((ext) => f.name.toLowerCase().endsWith(ext))) {
      setErrorMsg(`Unsupported file type. Choose ${videoExtensions.join(", ")}.`);
      return;
    }
    if (f.size === 0) {
      setErrorMsg("The selected file is empty.");
      return;
    }
    if (f.size > maxUploadBytes) {
      setErrorMsg(`File is too large (${formatBytes(f.size)}). Max allowed: ${formatBytes(maxUploadBytes)}.`);
      return;
    }
    setErrorMsg("");
    setFile(f);
    setFileDisplayName(f.name.replace(/\.[^/.]+$/, ""));
  }, [maxUploadBytes, videoExtensions]);

  const { data: sourcesData, isLoading: sourcesLoading, isError: sourcesError, refetch: refetchSources } = useQuery<SourceListResponse>({
    queryKey: ["sources-list"],
    queryFn: async () => {
      const first = (await apiClient.get<SourceListResponse>("/sources", { params: { per_page: 100 } })).data;
      const items = [...first.items];
      const totalPages = Math.ceil(first.total / 100);
      for (let page = 2; page <= totalPages; page++) {
        const next = (await apiClient.get<SourceListResponse>("/sources", { params: { page, per_page: 100 } })).data;
        items.push(...next.items);
      }
      return { ...first, items };
    },
    enabled: open && tab === "sync",
  });
  const activeSources = (sourcesData?.items ?? []).filter((source) => source.is_active);
  const search = sourceSearch.trim().toLocaleLowerCase();
  const visibleSources = search
    ? activeSources.filter((source) =>
      `${source.name} ${SOURCE_TYPE_LABELS[source.source_type] ?? source.source_type}`.toLocaleLowerCase().includes(search))
    : activeSources;
  const unselectedVisibleSources = visibleSources.filter((source) => !selectedSources.has(source.id));
  const selectVisibleExceedsLimit = selectedSources.size + unselectedVisibleSources.length > 50;

  useEffect(() => {
    const id = window.setTimeout(() => setDebouncedUrl(url.trim()), PREVIEW_DEBOUNCE_MS);
    return () => window.clearTimeout(id);
  }, [url]);

  useEffect(() => {
    const id = window.setTimeout(() => setDebouncedDiskUrl(diskUrl.trim()), PREVIEW_DEBOUNCE_MS);
    return () => window.clearTimeout(id);
  }, [diskUrl]);

  const previewReady =
    open && tab === "url" && debouncedUrl === url.trim() && isLikelySupportedUrl(debouncedUrl);

  const {
    data: preview,
    isFetching: previewLoading,
    isError: previewError,
    refetch: refetchPreview,
  } = useQuery({
    queryKey: ["formats-preview", debouncedUrl],
    queryFn: async () => {
      const res = await apiClient.post<FormatsPreviewResponse>("/recordings/formats-preview", {
        url: debouncedUrl,
      });
      return res.data;
    },
    enabled: previewReady,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
  const suggestedUrlName = previewReady ? collapseWhitespace(preview?.title ?? "").slice(0, 500) : "";

  const playlistPreviewReady = open && tab === "playlist" && debouncedUrl === url.trim()
    && isLikelyYoutubePlaylistUrl(debouncedUrl);
  const { data: playlistPreview, isFetching: playlistPreviewLoading, isError: playlistPreviewError } = useQuery({
    queryKey: ["playlist-preview", debouncedUrl],
    queryFn: async () => (await apiClient.post<PlaylistPreviewResponse>("/recordings/playlist-preview", {
      url: debouncedUrl,
    })).data,
    enabled: playlistPreviewReady,
    retry: false,
    staleTime: 5 * 60 * 1000,
  });

  const diskPreviewReady = open && tab === "disk" && debouncedDiskUrl === diskUrl.trim()
    && isLikelyDiskUrl(debouncedDiskUrl);
  const { data: diskPreview, isFetching: diskPreviewLoading, isError: diskPreviewError } = useQuery({
    queryKey: ["disk-preview", debouncedDiskUrl],
    queryFn: async () => (await apiClient.post<DiskPreviewResponse>("/recordings/disk-preview", {
      public_url: debouncedDiskUrl,
    })).data,
    enabled: diskPreviewReady,
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
  const suggestedDiskSourceName = diskPreviewReady && diskPreview
    ? (diskPreview.resource_type === "file" ? diskPreview.name.replace(/\.[^/.]+$/, "") : diskPreview.name).slice(0, 255)
    : "";
  const qualityReady = tab === "url"
    ? Boolean(previewReady && preview)
    : tab === "playlist" && Boolean(playlistPreviewReady && playlistPreview?.video_count);

  const addUrl = useMutation({
    mutationFn: (payload: { url: string; quality: string; auto_run: boolean; display_name?: string }) =>
      apiClient.post("/recordings/add-url", payload),
    onSuccess: (res, variables) => {
      invalidateRecordings();
      setSuccessMsg(variables.auto_run
        ? res.data?.task_id ? "Recording added. Processing started." : "Recording added, but processing could not start. Run it from the recording page."
        : "Recording added.");
      setUrl("");
      setUrlDisplayName(null);
    },
    onError: (err: unknown) => {
      setErrorMsg(extractApiError(err, "Failed to add URL"));
    },
  });

  const addPlaylist = useMutation({
    mutationFn: (payload: { url: string; quality: string; auto_run: boolean }) =>
      apiClient.post("/recordings/add-playlist", payload),
    onSuccess: (res, variables) => {
      invalidateRecordings();
      const count = res.data?.recordings_created ?? 0;
      const existing = res.data?.recordings_updated ?? 0;
      const failed = res.data?.recordings_failed ?? 0;
      const started = res.data?.task_ids?.length ?? 0;
      setSuccessMsg(`${count} added, ${existing} already present${failed ? `, ${failed} failed` : ""}${variables.auto_run ? `, ${started} processing started` : ""}.`);
      setUrl("");
    },
    onError: (err: unknown) => {
      setErrorMsg(extractApiError(err, "Failed to add playlist"));
    },
  });

  const uploadFile = useMutation({
    onMutate: () => { setUploadProgress(0); setResumedFrom(null); },
    mutationFn: async ({ f, displayName, run }: { f: File; displayName: string; run: boolean }) => {
      const name = collapseWhitespace(displayName) || f.name.replace(/\.[^/.]+$/, "");
      const fingerprint = await fileFingerprint(f);
      const key = `leap-upload:${fingerprint}`;
      let session: ResumableUploadStatus | null = null;
      const previousId = savedUploadId(key);
      if (previousId) {
        try {
          session = (await apiClient.get<ResumableUploadStatus>(`/recordings/uploads/${previousId}`)).data;
          if (session.fingerprint !== fingerprint || session.size !== f.size) session = null;
        } catch (error) {
          if (![404, 410].includes(httpStatus(error) ?? 0)) throw error;
        }
      }
      if (!session) {
        rememberUpload(key, null);
        session = (await apiClient.post<ResumableUploadStatus>("/recordings/uploads", {
          filename: f.name, size: f.size, display_name: name, auto_run: run, fingerprint,
        })).data;
        rememberUpload(key, session.upload_id);
      }
      if (!session.recording_id && (session.display_name !== name || session.auto_run !== run)) {
        session = (await apiClient.patch<ResumableUploadStatus>(`/recordings/uploads/${session.upload_id}`, {
          display_name: name, auto_run: run,
        })).data;
      }
      let offset = session.offset;
      if (offset > 0) setResumedFrom(Math.round((offset / f.size) * 100));
      setUploadProgress(Math.round((offset / f.size) * 100));
      while (offset < f.size) {
        const end = Math.min(offset + session.chunk_size, f.size);
        try {
          session = (await apiClient.put<ResumableUploadStatus>(
            `/recordings/uploads/${session.upload_id}/chunk`, f.slice(offset, end), {
              params: { offset },
              headers: { "Content-Type": "application/octet-stream" },
              onUploadProgress: (evt) => setUploadProgress(Math.round((Math.min(offset + evt.loaded, f.size) / f.size) * 100)),
            }
          )).data;
        } catch (error) {
          try {
            session = (await apiClient.get<ResumableUploadStatus>(`/recordings/uploads/${session.upload_id}`)).data;
          } catch { throw error; }
          if (session.offset === offset) throw error;
        }
        offset = session.offset;
      }
      const response = await apiClient.post<{ task_id: string | null }>(
        `/recordings/uploads/${session.upload_id}/complete`
      );
      rememberUpload(key, null);
      return response;
    },
    onSuccess: (res, variables) => {
      invalidateRecordings();
      setUploadProgress(null);
      setResumedFrom(null);
      setSuccessMsg(variables.run
        ? res.data.task_id ? "File uploaded. Processing started." : "File uploaded, but processing could not start. Run it from the recording page."
        : "File uploaded. Open the recording to start processing.");
      setFile(null);
      setFileDisplayName("");
    },
    onError: (err: unknown) => {
      setUploadProgress(null);
      setErrorMsg(httpStatus(err) === 413
        ? `File exceeds the server upload limit (${formatBytes(maxUploadBytes)}).`
        : httpStatus(err) === undefined
          ? "Connection lost. Select Upload file again to continue from the saved position."
        : extractApiError(err, "Failed to upload file"));
    },
  });

  const addDisk = useMutation({
    mutationFn: (payload: { public_url: string; name: string; resource_type: DiskKind; auto_run: boolean }) =>
      apiClient.post<{ source_id: number; task_id: string; reused: boolean }>("/recordings/add-disk-link", payload),
    onSuccess: (res, variables) => {
      qc.invalidateQueries({ queryKey: ["sources-list"] });
      setSyncTaskId(res.data.task_id);
      invalidateRecordings();
      setSuccessMsg(res.data.reused
        ? `Disk sync queued.${variables.auto_run ? " New videos will process after sync." : ""}`
        : `Disk source saved and sync queued.${variables.auto_run ? " New videos will process after sync." : ""}`);
    },
    onError: (err: unknown) => setErrorMsg(extractApiError(err, "Could not add Disk link")),
  });

  const syncSource = useMutation({
    mutationFn: ({ sourceIds, run }: { sourceIds: number[]; run: boolean }) =>
      apiClient.post("/sources/bulk/sync", { source_ids: sourceIds, auto_run: run }),
    onSuccess: (res, variables) => {
      setSyncTaskId(res.data.task_id);
      invalidateRecordings();
      setSuccessMsg(variables.run
        ? "Sync queued. Newly found videos will process after sync."
        : "Sync queued for the selected sources.");
    },
    onError: (err: unknown) => {
      setErrorMsg(extractApiError(err, "Failed to start sync"));
    },
  });

  const isLoading = addUrl.isPending || addPlaylist.isPending || addDisk.isPending || uploadFile.isPending || syncSource.isPending;

  const handleClose = useCallback(() => {
    if (isLoading) return;
    setTopTab("sync");
    setLinkTab("url");
    setUrl("");
    setUrlDisplayName(null);
    setQuality("best");
    setAutoRun(false);
    setDiskUrl("");
    setDiskKind("file");
    setDiskSourceName(null);
    setFile(null);
    setFileDisplayName("");
    setSelectedSources(new Set());
    setSourceSearch("");
    setSuccessMsg("");
    setErrorMsg("");
    setUploadProgress(null);
    setResumedFrom(null);
    onClose();
  }, [onClose, isLoading]);

  function handleSubmit() {
    if (isLoading || (syncFeedbackVisible && syncInFlight)) return;
    setSuccessMsg("");
    setErrorMsg("");
    if (tab === "url" || tab === "playlist") {
      const trimmed = url.trim();
      if (!trimmed) { setErrorMsg(tab === "url" ? "Enter a URL" : "Enter a playlist URL"); return; }
      if (!isLikelySupportedUrl(trimmed)) {
        setErrorMsg("Use a YouTube, VK Video, Rutube, or Vimeo link.");
        return;
      }
      if (tab === "playlist" && !isLikelyYoutubePlaylistUrl(trimmed)) {
        setErrorMsg("Enter a YouTube playlist link containing a list ID.");
        return;
      }
      const payload = { url: trimmed, quality, auto_run: autoRun };
      if (tab === "url") {
        if (!previewReady || !preview) { setErrorMsg("Wait for the video preview before adding it."); return; }
        const name = collapseWhitespace(urlDisplayName ?? suggestedUrlName);
        if (urlDisplayName !== null && !name) { setErrorMsg("Recording name is required"); return; }
        if (name.length > 500) { setErrorMsg("Recording name must be 500 characters or fewer"); return; }
        addUrl.mutate({ ...payload, ...(name ? { display_name: name } : {}) });
      }
      else {
        if (!playlistPreviewReady || !playlistPreview?.video_count) {
          setErrorMsg("Wait for a playlist with available videos to load.");
          return;
        }
        addPlaylist.mutate(payload);
      }
    } else if (tab === "disk") {
      const link = diskUrl.trim();
      const name = collapseWhitespace(diskSourceName ?? suggestedDiskSourceName);
      if (!isLikelyDiskUrl(link)) { setErrorMsg("Enter a public Yandex Disk link"); return; }
      if (!diskPreviewReady || !diskPreview?.video_count) {
        setErrorMsg("Wait for a Disk link with supported videos to load.");
        return;
      }
      if (diskPreview.resource_type !== diskKind) {
        setErrorMsg(`This link points to ${diskPreview.resource_type === "dir" ? "a folder" : "one file"}. Select the matching type.`);
        return;
      }
      if (name.length < 3 || name.length > 255) { setErrorMsg("Source name must be 3–255 characters"); return; }
      setSyncTaskId(null);
      addDisk.mutate({ public_url: link, name, resource_type: diskKind, auto_run: autoRun });
    } else if (tab === "file") {
      if (!file) { setErrorMsg("Select a file"); return; }
      if (file.size > maxUploadBytes) {
        setErrorMsg(`File is too large (${formatBytes(file.size)}). Max allowed: ${formatBytes(maxUploadBytes)}.`);
        return;
      }
      const name = collapseWhitespace(fileDisplayName);
      if (!name || name.length > 500) {
        setErrorMsg("Recording name must be 1–500 characters");
        return;
      }
      uploadFile.mutate({ f: file, displayName: name, run: autoRun });
    } else if (tab === "sync") {
      if (selectedSources.size === 0) { setErrorMsg("Select at least one source"); return; }
      if (selectedSources.size > 50) { setErrorMsg("Select up to 50 sources per sync."); return; }
      setSyncTaskId(null);
      syncSource.mutate({ sourceIds: Array.from(selectedSources), run: autoRun });
    }
  }

  const submitLabel =
    tab === "url" ? "Add video" :
    tab === "playlist" ? "Add playlist" :
    tab === "disk" ? "Save & sync" :
    tab === "file" ? "Upload file" :
    "Start sync";

  return (
    <Modal open={open} onClose={handleClose} labelledBy={titleId} panelClassName="max-w-lg overflow-hidden">
      <div className="flex max-h-[calc(100dvh-2rem)] flex-col bg-card">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h2 id={titleId} className="text-sm font-semibold text-foreground">Add video</h2>
          <button
            type="button"
            onClick={handleClose}
            disabled={isLoading}
            aria-label="Close dialog"
            className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
          >
            <X size={18} />
          </button>
        </div>

        {/* Tabs */}
        <div className="border-b border-border px-6 pt-4">
          <Tabs
            items={TABS}
            value={topTab}
            onChange={(next) => { setTopTab(next); setSuccessMsg(""); setErrorMsg(""); }}
            label="Add video method"
            idPrefix={titleId}
            panelId={`${titleId}-panel`}
            hidePanel
            disabled={isLoading}
            stretch
            tablistClassName="mb-3"
          >
            {null}
          </Tabs>
        </div>

        {/* Body */}
        <div
          id={`${titleId}-panel`}
          role="tabpanel"
          aria-labelledby={`${titleId}-tab-${topTab}`}
          className="min-h-0 flex-1 space-y-4 overflow-y-auto px-6 py-5"
        >
          {topTab === "link" && (
            <SegmentedField
              label="Link type"
              value={linkTab}
              options={LINK_TYPES}
              onChange={(next) => { setLinkTab(next); setQuality("best"); setSuccessMsg(""); setErrorMsg(""); }}
              disabled={isLoading}
              stretch
            />
          )}
          {(tab === "url" || tab === "playlist") && (
            <>
              <div>
                <label htmlFor={`${titleId}-url`} className={FILTER_LABEL}>
                  {tab === "url" ? "Video link" : "YouTube playlist link"}
                </label>
                <div className="flex gap-2">
                  <input
                    id={`${titleId}-url`}
                    type="url"
                    value={url}
                    onChange={(e) => { setUrl(e.target.value); setUrlDisplayName(null); setQuality("best"); }}
                    disabled={isLoading}
                    placeholder={tab === "url" ? "https://youtube.com/watch?v=..." : "https://youtube.com/playlist?list=..."}
                    className={cn(FILTER_CONTROL, "min-w-0 flex-1")}
                  />
                  {tab === "url" && isLikelySupportedUrl(url.trim()) && (
                    <button
                      type="button"
                      onClick={() => void refetchPreview()}
                      disabled={isLoading || !previewReady || previewLoading}
                      title="Refresh preview"
                      aria-label="Refresh preview"
                      className="pressable flex size-[2.875rem] shrink-0 items-center justify-center rounded-xl border border-border text-secondary-foreground hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 disabled:opacity-50"
                    >
                      {previewLoading
                        ? <Loader2 size={14} className="animate-spin" />
                        : <ScanLine size={14} />}
                    </button>
                  )}
                </div>
                {tab === "url" && (
                  <p className="mt-1.5 text-xs text-muted-foreground">YouTube · VK Video · Rutube · Vimeo</p>
                )}
                {tab === "playlist" && url.trim() && !isLikelyYoutubePlaylistUrl(url.trim()) && (
                  <p className="mt-1.5 text-xs text-danger-fg">Use a YouTube playlist link containing a list ID.</p>
                )}
                {tab === "url" && previewReady && previewLoading && !preview && (
                  <div className="mt-2 aspect-video animate-pulse rounded-xl bg-muted" />
                )}
                {tab === "url" && previewReady && preview && (
                  <UrlLinkPreview
                    key={preview.thumbnail ?? preview.title}
                    title={preview.title}
                    thumbnail={preview.thumbnail}
                    duration={preview.duration}
                  />
                )}
                {tab === "url" && (
                  <Field label="Recording name" className="mt-3">
                    <input
                      type="text"
                      value={urlDisplayName ?? suggestedUrlName}
                      onChange={(e) => setUrlDisplayName(e.target.value)}
                      disabled={isLoading}
                      maxLength={500}
                      placeholder="Use the video title or enter a name"
                      className={FILTER_CONTROL}
                    />
                  </Field>
                )}
                {tab === "url" && previewReady && previewError && (
                  <p className="mt-1.5 text-xs text-danger-fg">Could not inspect this video. Check the link or try again.</p>
                )}
                {tab === "playlist" && playlistPreviewReady && playlistPreviewLoading && !playlistPreview && (
                  <p className="mt-2 text-xs text-muted-foreground">Inspecting playlist…</p>
                )}
                {tab === "playlist" && playlistPreviewReady && playlistPreviewError && (
                  <p className="mt-2 text-xs text-danger-fg">Could not inspect this playlist. Check the link or try again.</p>
                )}
                {tab === "playlist" && playlistPreviewReady && playlistPreview && (
                  <div className="mt-3 rounded-xl border border-border bg-muted/30 p-3 text-sm">
                    <p className="font-medium text-foreground">{playlistPreview.video_count} videos found · one recording each</p>
                    {playlistPreview.unavailable_count > 0 && (
                      <p className="mt-1 text-xs text-danger-fg">{playlistPreview.unavailable_count} unavailable videos will be skipped.</p>
                    )}
                    {playlistPreview.sample_titles.length > 0 && (
                      <p className="mt-1 truncate text-xs text-muted-foreground" title={playlistPreview.sample_titles.join(", ")}>
                        {playlistPreview.sample_titles.join(" · ")}
                      </p>
                    )}
                  </div>
                )}
              </div>
              <div className="space-y-1.5">
                <Field label={tab === "playlist" ? "Max quality per video" : "Max quality"}>
                  <NativeSelect
                    value={quality}
                    onChange={(e) => setQuality(e.target.value)}
                    disabled={isLoading || !qualityReady}
                  >
                    {qualityReady
                      ? (tab === "url" && preview
                        ? buildFormatOptions(preview.formats)
                        : STATIC_QUALITY_OPTIONS
                      ).map((option) => (
                        <option key={option.value} value={option.value}>{option.label}</option>
                      ))
                      : <option value="best">Check link first</option>}
                  </NativeSelect>
                </Field>
                {qualityReady && quality !== "best" && (
                  <p className="text-xs text-muted-foreground">Actual quality may be lower.</p>
                )}
              </div>
            </>
          )}

          {tab === "disk" && (
            <div className="space-y-4">
              <SegmentedField
                label="Disk resource"
                value={diskKind}
                options={DISK_TYPES}
                onChange={(next) => { setDiskKind(next); setErrorMsg(""); }}
                disabled={isLoading}
                stretch
              />
              <Field label="Public Yandex Disk link">
                <input
                  type="url"
                  value={diskUrl}
                  onChange={(e) => { setDiskUrl(e.target.value); setDiskSourceName(null); setErrorMsg(""); }}
                  disabled={isLoading}
                  placeholder="https://disk.yandex.ru/d/..."
                  className={FILTER_CONTROL}
                />
              </Field>
              {diskUrl.trim() && !isLikelyDiskUrl(diskUrl.trim()) && (
                <p className="text-xs text-danger-fg">Use a public Yandex Disk sharing link.</p>
              )}
              {diskPreviewReady && diskPreviewLoading && !diskPreview && (
                <p className="text-xs text-muted-foreground">Inspecting Disk link…</p>
              )}
              {diskPreviewReady && diskPreviewError && (
                <p className="text-xs text-danger-fg">Could not inspect this public link. Check sharing access and try again.</p>
              )}
              {diskPreviewReady && diskPreview && (
                <div className="rounded-xl border border-border bg-muted/30 p-3 text-sm">
                  <p className="font-medium text-foreground">{diskPreview.name}: {diskPreview.video_count} video{diskPreview.video_count === 1 ? "" : "s"}</p>
                  {diskPreview.resource_type !== diskKind && (
                    <p className="mt-1 text-xs text-danger-fg">This link is {diskPreview.resource_type === "dir" ? "a folder" : "one file"}. Select that type above.</p>
                  )}
                  {diskPreview.video_count === 0 && (
                    <p className="mt-1 text-xs text-danger-fg">No supported video files found.</p>
                  )}
                  {diskPreview.sample_names.length > 0 && (
                    <p className="mt-1 truncate text-xs text-muted-foreground" title={diskPreview.sample_names.join(", ")}>
                      {diskPreview.sample_names.join(" · ")}
                    </p>
                  )}
                </div>
              )}
              <Field label="Source name">
                <input
                  type="text"
                  value={diskSourceName ?? suggestedDiskSourceName}
                  onChange={(e) => { setDiskSourceName(e.target.value); setErrorMsg(""); }}
                  disabled={isLoading}
                  maxLength={255}
                  placeholder="Course recordings"
                  className={FILTER_CONTROL}
                />
              </Field>
              <p className="text-xs text-muted-foreground">
                {diskKind === "dir" ? "Includes subfolders · Original quality" : "One video · Original quality"}
              </p>
            </div>
          )}

          {tab === "file" && (
            <div className="space-y-3">
              <div>
                <label htmlFor={`${titleId}-file`} className={FILTER_LABEL}>Video file</label>
                <div
                  role="button"
                  tabIndex={isLoading ? -1 : 0}
                  aria-disabled={isLoading}
                  aria-label={file ? `Replace ${file.name}` : "Choose video file"}
                  className={cn(
                    "pressable pressable-block cursor-pointer rounded-xl border border-dashed px-4 py-6 text-center focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30",
                    isLoading && "cursor-not-allowed opacity-50",
                    isDragging
                      ? "border-primary bg-primary/10"
                      : file
                        ? "border-primary bg-primary/5"
                        : "border-input bg-muted/20 hover:border-primary/50 hover:bg-muted/30"
                  )}
                  onClick={() => { if (!isLoading) fileRef.current?.click(); }}
                  onKeyDown={(e) => {
                    if ((e.key === "Enter" || e.key === " ") && !isLoading) {
                      e.preventDefault();
                      fileRef.current?.click();
                    }
                  }}
                  onDragOver={(e) => { e.preventDefault(); if (!isLoading) setIsDragging(true); }}
                  onDragLeave={(e) => { e.preventDefault(); setIsDragging(false); }}
                  onDrop={(e) => {
                    e.preventDefault();
                    setIsDragging(false);
                    if (isLoading) return;
                    if (e.dataTransfer.files.length > 1) {
                      setFile(null);
                      setFileDisplayName("");
                      setErrorMsg("Choose one video file at a time.");
                      return;
                    }
                    acceptFile(e.dataTransfer.files?.[0] ?? null);
                  }}
                >
                  <Upload size={24} className="mx-auto mb-2 text-muted-foreground" />
                  {file ? (
                    <p className="break-all text-sm font-medium text-primary">{file.name}</p>
                  ) : (
                    <>
                      <p className="text-sm font-medium text-secondary-foreground">Drag &amp; drop a video file, or click to select</p>
                      <p className="mt-1 text-xs text-muted-foreground">Up to {formatBytes(maxUploadBytes)}</p>
                    </>
                  )}
                  <input
                    id={`${titleId}-file`}
                    ref={fileRef}
                    type="file"
                    accept={videoExtensions.join(",")}
                    className="hidden"
                    disabled={isLoading}
                    onClick={(e) => e.stopPropagation()}
                    onChange={(e) => {
                      acceptFile(e.target.files?.[0] ?? null);
                      e.target.value = "";
                    }}
                  />
                </div>
              </div>
              <Field label="Recording name">
                <input
                  type="text"
                  value={fileDisplayName}
                  onChange={(e) => setFileDisplayName(e.target.value)}
                  maxLength={500}
                  disabled={isLoading}
                  placeholder={file ? file.name.replace(/\.[^/.]+$/, "") : "Enter recording name"}
                  className={FILTER_CONTROL}
                />
              </Field>
              <span className="inline-flex rounded-lg border border-border bg-muted/40 px-2.5 py-1.5 text-xs text-muted-foreground">
                Resume: same file · {uploadPolicy?.resume_hours ?? 24}h
              </span>
              {uploadFile.isPending && uploadProgress !== null && (
                <div className="space-y-1">
                  {resumedFrom !== null && (
                    <p className="text-xs text-muted-foreground">Resumed from {resumedFrom}% already on the server.</p>
                  )}
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>{uploadProgress < 100 ? "Uploading…" : "Saving…"}</span>
                    {uploadProgress < 100 && (
                      <span className="tabular-nums">{uploadProgress}%</span>
                    )}
                  </div>
                  {uploadProgress < 100 ? (
                    <ProgressBar variant="determinate" value={uploadProgress} />
                  ) : (
                    <ProgressBar variant="indeterminate" />
                  )}
                </div>
              )}
            </div>
          )}

          {tab === "sync" && (
            <div>
              {sourcesLoading ? (
                <p className="py-4 text-center text-sm text-muted-foreground">Loading sources…</p>
              ) : sourcesError ? (
                <div className="py-4 text-center text-sm text-danger-fg">
                  <p>Could not load sources.</p>
                  <button type="button" onClick={() => void refetchSources()} className="mt-2 text-primary hover:underline">Retry</button>
                </div>
              ) : activeSources.length === 0 ? (
                <div className="py-4 text-center text-sm text-muted-foreground">
                  <p>No active sources.</p>
                  <Link href="/sources" className="mt-2 inline-block text-primary hover:underline">Manage sources</Link>
                </div>
              ) : (
                <div className="space-y-3">
                  {activeSources.length > 8 && (
                    <input
                      type="search"
                      value={sourceSearch}
                      onChange={(event) => setSourceSearch(event.target.value)}
                      aria-label="Search sources"
                      placeholder="Search sources"
                      className={FILTER_CONTROL}
                    />
                  )}
                  <div className="flex items-center justify-end gap-3 text-xs">
                    {unselectedVisibleSources.length > 0 && (
                      <button
                        type="button"
                        onClick={() => setSelectedSources((previous) => {
                          const next = new Set(previous);
                          for (const source of visibleSources) {
                            if (next.size >= 50) break;
                            next.add(source.id);
                          }
                          return next;
                        })}
                        disabled={isLoading || selectedSources.size >= 50}
                        className="text-primary hover:underline disabled:opacity-50"
                      >
                        {selectVisibleExceedsLimit ? "Select up to 50" : search ? "Select shown" : "Select all"}
                      </button>
                    )}
                    {selectedSources.size > 0 && (
                      <button type="button" onClick={() => setSelectedSources(new Set())} disabled={isLoading} className="text-muted-foreground hover:text-foreground disabled:opacity-50">Clear</button>
                    )}
                  </div>
                  {visibleSources.length === 0 && (
                    <p className="py-4 text-center text-sm text-muted-foreground">No matching sources.</p>
                  )}
                  {visibleSources.map((s) => (
                    <label key={s.id} className="pressable pressable-block flex min-h-11 cursor-pointer items-center gap-3 rounded-xl border border-border px-3 py-2.5 hover:bg-muted">
                      <input
                        type="checkbox"
                        checked={selectedSources.has(s.id)}
                        disabled={isLoading || (!selectedSources.has(s.id) && selectedSources.size >= 50)}
                        onChange={() => {
                          setSelectedSources((prev) => {
                            const next = new Set(prev);
                            if (next.has(s.id)) next.delete(s.id);
                            else if (next.size < 50) next.add(s.id);
                            return next;
                          });
                        }}
                        className={CHECKBOX}
                      />
                      <span className="min-w-0 flex-1 truncate text-sm font-medium text-foreground" title={s.name}>{s.name}</span>
                      <span className="shrink-0 rounded-md bg-muted px-2 py-0.5 text-xs text-muted-foreground">{SOURCE_TYPE_LABELS[s.source_type] ?? s.source_type}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>
          )}

          <label className="flex cursor-pointer items-center gap-2 text-sm text-secondary-foreground">
            <input
              type="checkbox"
              checked={autoRun}
              onChange={(e) => setAutoRun(e.target.checked)}
              disabled={isLoading}
              className={CHECKBOX}
            />
            {tab === "file" ? "Process after upload" :
              tab === "sync" || tab === "disk" ? "Download & process after sync" :
              "Download & process after adding"}
          </label>

          {visibleError && (
            <p role="alert" className="text-sm text-danger-fg bg-danger-fg/10 px-3 py-2 rounded-xl">{visibleError}</p>
          )}
          {visibleSuccess && (
            <p role="status" className="text-sm text-success-fg bg-success-fg/10 px-3 py-2 rounded-xl">{visibleSuccess}</p>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-3 border-t border-border px-6 py-4">
          <ActionButton variant="secondary" onClick={handleClose} disabled={isLoading}>
            Close
          </ActionButton>
          <ActionButton
            onClick={handleSubmit}
            disabled={tab === "sync" && selectedSources.size === 0}
            isPending={isLoading || (syncFeedbackVisible && syncInFlight)}
            pendingLabel={
              uploadFile.isPending && uploadProgress !== null
                ? uploadProgress < 100 ? `${uploadProgress}%` : "Saving…"
                : syncFeedbackVisible && syncInFlight ? "Syncing…"
                : addPlaylist.isPending ? "Importing…"
                : addUrl.isPending ? "Adding…"
                : "Queuing…"
            }
          >
            {submitLabel}
          </ActionButton>
        </div>
      </div>
    </Modal>
  );
}
