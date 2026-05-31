"use client";

import { use, useState, type ComponentType, type ReactNode } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft, Play, Pause, Trash2, Upload, ExternalLink,
  CheckCircle2, XCircle, Clock, Loader2, SkipForward, RotateCcw, Settings2, ChevronDown, ArchiveRestore, FilePlus2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/api/client";
import { StatusBadge, type ProcessingStatus } from "@/components/ui/status-badge";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { RunConfigModal } from "@/components/recordings/run-config-modal";
import { ACTIVE_POLL_STATUSES, POLL_INTERVAL_DETAIL } from "@/lib/constants";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ProcessingStage {
  stage_type: string;
  status: string;
  failed: boolean;
  failed_reason: string | null;
  started_at: string | null;
  completed_at: string | null;
  retry_count: number;
}

interface OutputTarget {
  id: number;
  target_type: string;
  status: string;
  target_meta: Record<string, unknown>;
  failed: boolean;
  failed_reason: string | null;
  uploaded_at: string | null;
  preset: { id: number; name: string } | null;
}

interface SourceResponse {
  source_type: string;
  source_key: string;
  metadata: Record<string, unknown>;
}

interface TopicTimestamp {
  topic: string;
  start: number;
  end?: number;
}

interface TopicVersion {
  id?: string;
  topic_timestamps?: TopicTimestamp[];
}

interface TopicsData {
  exists: boolean;
  active_version?: string;
  versions?: TopicVersion[];
}

interface VideoVariantInfo {
  exists: boolean;
  path?: string;
  size_mb?: number | null;
}

interface SubtitleVariantInfo {
  path: string | null;
  exists: boolean;
  size_kb?: number | null;
}

interface TranscriptionDetail {
  exists: boolean;
  files?: {
    master?: string;
    segments_txt?: string;
    words_txt?: string;
  };
}

interface RecordingDetail {
  id: number;
  display_name: string;
  status: ProcessingStatus;
  start_time: string;
  duration: number;
  failed: boolean;
  failed_reason: string | null;
  failed_at_stage?: string | null;
  on_pause: boolean;
  source: SourceResponse | null;
  outputs: OutputTarget[];
  processing_stages: ProcessingStage[];
  pipeline_started_at: string | null;
  pipeline_completed_at: string | null;
  soft_deleted_at?: string | null;
  pipeline_duration_seconds: number | null;
  is_mapped: boolean;
  template_id: number | null;
  template_name?: string | null;
  video_file_size: number | null;
  created_at: string;
  can_run: boolean;
  can_pause: boolean;
  ready_to_upload: boolean;
  topics?: TopicsData;
  videos?: Record<string, VideoVariantInfo> | null;
  subtitles?: Record<string, SubtitleVariantInfo> | null;
  transcription?: TranscriptionDetail | null;
  upload_summary?: { total: number; uploaded: number; failed: number; partial: boolean } | null;
}

interface RecordingConfigResponse {
  recording_id: number;
  is_mapped: boolean;
  template_id: number | null;
  template_name: string | null;
  has_manual_override: boolean;
  processing_config: {
    transcription?: {
      language?: string;
      granularity?: string;
      enable_transcription?: boolean;
      enable_topics?: boolean;
      enable_subtitles?: boolean;
    };
  } | null;
  output_config: {
    auto_upload?: boolean;
    upload_captions?: boolean;
    preset_ids?: number[];
  } | null;
  metadata_config: {
    title_template?: string;
    description_template?: string;
    youtube?: Record<string, unknown>;
    vk?: Record<string, unknown>;
    yandex_disk?: Record<string, unknown>;
  } | null;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("ru-RU", { day: "numeric", month: "short", year: "numeric" });
}

function formatDuration(seconds: number) {
  if (!seconds) return "—";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function formatTimecode(seconds: number) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function formatFileSize(bytes: number) {
  if (bytes > 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`;
  if (bytes > 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(0)} MB`;
  return `${(bytes / 1024).toFixed(0)} KB`;
}

function formatStageDuration(startedAt: string | null, completedAt: string | null): string {
  if (!startedAt || !completedAt) return "";
  const ms = new Date(completedAt).getTime() - new Date(startedAt).getTime();
  if (!Number.isFinite(ms) || ms < 0) return "";
  const secTotal = Math.floor(ms / 1000);
  const h = Math.floor(secTotal / 3600);
  const m = Math.floor((secTotal % 3600) / 60);
  const s = secTotal % 60;
  if (h > 0) return `${h}ч ${m}м`;
  if (m > 0) return `${m}м ${s}с`;
  return `${s}с`;
}

function formatDateTimeShort(iso: string): string {
  return new Date(iso).toLocaleString("ru-RU", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Sidebar/detail template line with optional link to /templates/:id (preset row styling). */
function renderRecordingTemplateNavValue(opts: {
  isMapped: boolean;
  templateId: number | null;
  templateName: string | null;
}): ReactNode {
  const { isMapped, templateId, templateName } = opts;
  if (!isMapped) return "Не привязан";
  const tid = templateId ?? null;
  const nameTrimmed = templateName?.trim();
  const name = nameTrimmed ? nameTrimmed : null;
  if (tid != null) {
    const linkText = name ?? `#${tid}`;
    return (
      <Link
        href={`/templates/${tid}`}
        title={linkText}
        className="inline-block truncate text-[11px] text-gray-900 transition-colors hover:text-[#224C87]"
      >
        {linkText}
      </Link>
    );
  }
  if (name) return name;
  return "Привязан";
}

// ---------------------------------------------------------------------------
// Pipeline stage helpers
// ---------------------------------------------------------------------------

const CANONICAL_STAGE_ORDER = ["DOWNLOAD", "TRIM", "TRANSCRIBE", "EXTRACT_TOPICS", "GENERATE_SUBTITLES"] as const;

const STAGE_TYPE_ALIASES: Record<string, string> = {
  TRANSCRIPTION: "TRANSCRIBE",
  SUBTITLES: "GENERATE_SUBTITLES",
};

function normalizeStageType(stageType: string): string {
  return STAGE_TYPE_ALIASES[stageType] ?? stageType;
}

const STAGE_META: Record<string, { name: string }> = {
  DOWNLOAD:           { name: "Загрузка" },
  TRIM:               { name: "Обрезка" },
  TRANSCRIBE:         { name: "Транскрипция" },
  EXTRACT_TOPICS:     { name: "Темы" },
  GENERATE_SUBTITLES: { name: "Субтитры" },
  UPLOAD:             { name: "Публикация" },
};

type LifecyclePhase = "pending" | "active" | "done" | "failed" | "skipped";

function phaseToStageStatus(phase: LifecyclePhase): string {
  switch (phase) {
    case "done":    return "COMPLETED";
    case "active":  return "IN_PROGRESS";
    case "failed":  return "FAILED";
    case "skipped": return "SKIPPED";
    default:        return "PENDING";
  }
}

function deriveIngressLifecycle(recording: RecordingDetail): { phase: LifecyclePhase; hint?: string } {
  const st = recording.status;
  const fs = (recording.failed_at_stage ?? "").toLowerCase();

  if (recording.failed && (fs === "download" || fs === "downloading")) {
    return { phase: "failed", hint: recording.failed_reason ?? undefined };
  }
  if (st === "DOWNLOADING") return { phase: "active" };
  if (st === "PENDING_SOURCE" || st === "INITIALIZED") return { phase: "pending" };
  if (st === "EXPIRED") return { phase: "skipped", hint: "Запись недоступна или истекла" };
  if (["DOWNLOADED", "PROCESSING", "PROCESSED", "UPLOADING", "UPLOADED", "READY", "SKIPPED"].includes(st)) {
    return { phase: "done" };
  }
  return { phase: "pending" };
}

const STAGE_STATUS_CONFIG: Record<string, { icon: ComponentType<{ size?: number; className?: string }>; dot: string }> = {
  COMPLETED:   { icon: CheckCircle2, dot: "bg-green-500" },
  FAILED:      { icon: XCircle,      dot: "bg-red-500" },
  IN_PROGRESS: { icon: Loader2,      dot: "bg-blue-500" },
  SKIPPED:     { icon: SkipForward,  dot: "bg-gray-300" },
  PENDING:     { icon: Clock,        dot: "bg-gray-300" },
};

const ICON_COLOR: Record<string, string> = {
  COMPLETED:   "text-green-500",
  FAILED:      "text-red-500",
  IN_PROGRESS: "text-blue-500",
  SKIPPED:     "text-gray-400",
  PENDING:     "text-gray-400",
};

const TARGET_LABELS: Record<string, string> = {
  YOUTUBE:     "YouTube",
  VK:          "VK",
  YANDEX_DISK: "Yandex Disk",
};

const PLATFORM_STATUS_CONFIG: Record<string, { icon: ComponentType<{ size?: number; className?: string }>; label: string; color: string }> = {
  UPLOADED:     { icon: CheckCircle2, label: "Опубликовано", color: "text-green-600" },
  UPLOADING:    { icon: Loader2,      label: "Публикуется…", color: "text-blue-600" },
  FAILED:       { icon: XCircle,      label: "Ошибка",       color: "text-red-600" },
  NOT_UPLOADED: { icon: Clock,        label: "Не загружено", color: "text-gray-400" },
};


// ---------------------------------------------------------------------------
// PipelineCompactRow — compact, no description line
// ---------------------------------------------------------------------------

function PipelineCompactRow({ stage }: { stage: ProcessingStage }) {
  const canon = normalizeStageType(stage.stage_type);
  const status = stage.failed ? "FAILED" : stage.status.toUpperCase();
  const cfg = STAGE_STATUS_CONFIG[status] ?? STAGE_STATUS_CONFIG["PENDING"];
  const Icon = cfg.icon;
  const name = STAGE_META[canon]?.name ?? stage.stage_type;
  const dur = formatStageDuration(stage.started_at, stage.completed_at);

  return (
    <div className="flex items-center gap-2 py-1.5">
      <Icon
        size={13}
        className={cn(
          ICON_COLOR[status] ?? "text-gray-400",
          status === "IN_PROGRESS" && "animate-spin"
        )}
      />
      <span className="flex-1 text-xs font-medium text-gray-700">{name}</span>
      {stage.retry_count > 0 && (
        <span className="text-[10px] text-amber-500">×{stage.retry_count}</span>
      )}
      {dur && <span className="shrink-0 text-[10px] tabular-nums text-gray-400">{dur}</span>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// PlatformOutputRow — used inside the Publications sidebar card
// ---------------------------------------------------------------------------

function PlatformOutputRow({
  output,
  readyToUpload,
  onUpload,
  uploadPending,
}: {
  output: OutputTarget;
  readyToUpload: boolean;
  onUpload: (targetType: string) => void;
  uploadPending: boolean;
}) {
  const ostatus = output.failed ? "FAILED" : output.status;
  const cfg = PLATFORM_STATUS_CONFIG[ostatus] ?? PLATFORM_STATUS_CONFIG["NOT_UPLOADED"];
  const Icon = cfg.icon;
  const label = TARGET_LABELS[output.target_type] ?? output.target_type;
  const url = output.target_meta?.video_url as string | undefined;
  const canUpload = readyToUpload && output.status === "NOT_UPLOADED";

  return (
    <div className="flex items-start gap-2.5 py-2.5">
      <Icon
        size={14}
        className={cn(cfg.color, "mt-0.5 shrink-0", ostatus === "UPLOADING" && "animate-spin")}
      />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
          <span className="text-xs font-semibold text-gray-900">{label}</span>
          {output.preset && (
            <Link
              href={`/presets/${output.preset.id}`}
              className="text-[11px] text-gray-400 transition-colors hover:text-[#224C87]"
            >
              {output.preset.name}
            </Link>
          )}
        </div>
        <p className={cn("text-[11px]", cfg.color)}>{cfg.label}</p>
        {output.failed_reason && (
          <p className="break-words text-[11px] text-red-500">{output.failed_reason}</p>
        )}
        {output.uploaded_at && (
          <p className="text-[10px] text-gray-400">{formatDateTimeShort(output.uploaded_at)}</p>
        )}
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1">
        {url && output.status === "UPLOADED" && (
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-0.5 text-[11px] font-medium text-[#224C87] hover:underline"
          >
            Открыть <ExternalLink size={10} />
          </a>
        )}
        {(canUpload || output.status === "FAILED") && (
          <button
            type="button"
            onClick={() => onUpload(output.target_type)}
            disabled={uploadPending}
            className="flex items-center gap-1 rounded-lg border border-[#D9D9D9] bg-white px-2 py-0.5 text-[11px] font-medium transition-colors hover:border-[#224C87] hover:bg-[#224C87] hover:text-white disabled:opacity-40"
          >
            <Upload size={10} />
            {output.status === "FAILED" ? "Retry" : "Upload"}
          </button>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// RecordingVideoPlayer
// ---------------------------------------------------------------------------

function RecordingVideoPlayer({
  recordingId,
  variant,
  sizeLabel,
}: {
  recordingId: string;
  variant: "processed" | "original";
  sizeLabel?: string;
}) {
  const [src, setSrc] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [loadError, setLoadError] = useState<string | null>(null);

  function loadVideo() {
    setLoading(true);
    setLoadError(null);
    setProgress(0);

    // Backend now returns a presigned URL that points directly at Object Storage.
    // The <video> element handles streaming + Range requests natively — no need
    // to download the full blob through the API.
    void apiClient
      .get<{ url: string; expires_in: number }>(`/recordings/${recordingId}/media?type=${variant}`)
      .then((res) => {
        setSrc(res.data.url);
      })
      .catch(() => setLoadError("Не удалось загрузить видео"))
      .finally(() => setLoading(false));
  }

  if (src) {
    return (
      <video
        src={src}
        controls
        preload="metadata"
        className="w-full rounded-xl bg-black max-h-[min(480px,70vh)]"
      />
    );
  }

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-[#EFEFEF] bg-gray-50 py-12">
        <div className="h-1.5 w-48 overflow-hidden rounded-full bg-gray-200">
          <div
            className="h-full rounded-full bg-[#224C87] transition-all duration-300"
            style={{ width: `${progress || 2}%` }}
          />
        </div>
        <p className="text-xs text-gray-400">
          Загрузка{progress > 0 ? ` ${progress}%` : "…"}
        </p>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-xl border border-red-100 bg-red-50 py-10">
        <p className="text-sm text-red-500">{loadError}</p>
        <button type="button" onClick={loadVideo} className="text-xs text-[#224C87] hover:underline">
          Повторить
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-[#EFEFEF] bg-gray-50 py-12">
      <button
        type="button"
        onClick={loadVideo}
        className="flex items-center gap-2 rounded-xl border border-[#D9D9D9] bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm transition-colors hover:border-[#224C87] hover:bg-[#224C87] hover:text-white"
      >
        Загрузить видео
      </button>
      {sizeLabel && <p className="text-xs text-gray-400">{sizeLabel}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Collapsible card helper
// ---------------------------------------------------------------------------

function CollapsibleCard({
  title,
  defaultOpen = false,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-2xl border border-[#D9D9D9] bg-white shadow-sm">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-5 py-4 text-left"
      >
        <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500">{title}</h2>
        <ChevronDown
          size={15}
          className={cn("text-gray-400 transition-transform duration-200", open && "rotate-180")}
        />
      </button>
      {open && <div className="border-t border-[#F0F0F0] px-5 pb-5 pt-4">{children}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function RecordingDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const qc = useQueryClient();
  const [videoTabChoice, setVideoTabChoice] = useState<"processed" | "original" | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [resetConfirm, setResetConfirm] = useState(false);
  const [resetDeleteFiles, setResetDeleteFiles] = useState(false);
  const [runConfigOpen, setRunConfigOpen] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [mediaDownloadError, setMediaDownloadError] = useState<string | null>(null);
  const [createTemplateOpen, setCreateTemplateOpen] = useState(false);
  const [createTemplateName, setCreateTemplateName] = useState("");

  // Config is loaded eagerly so template_name is available for Info sidebar
  const { data: recordingConfig, isLoading: configLoading } = useQuery<RecordingConfigResponse>({
    queryKey: ["recording-config", Number(id)],
    queryFn: async () => (await apiClient.get<RecordingConfigResponse>(`/recordings/${id}/config`)).data,
  });

  const { data: recording, isLoading, error } = useQuery<RecordingDetail>({
    queryKey: ["recording", id],
    queryFn: async () => {
      const res = await apiClient.get<RecordingDetail>(`/recordings/${id}?detailed=true`);
      return res.data;
    },
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s && ACTIVE_POLL_STATUSES.has(s) ? POLL_INTERVAL_DETAIL : false;
    },
    refetchIntervalInBackground: false,
  });

  const run = useMutation({
    mutationFn: () => apiClient.post(`/recordings/${id}/run`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["recording", id] }),
  });

  const pause = useMutation({
    mutationFn: () => apiClient.post(`/recordings/${id}/pause`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["recording", id] }),
  });

  const deleteRec = useMutation({
    mutationFn: () => apiClient.delete(`/recordings/${id}`),
    onSuccess: () => router.push("/recordings"),
  });

  const resetRec = useMutation({
    mutationFn: () => apiClient.post(`/recordings/${id}/reset`, null, { params: { delete_files: resetDeleteFiles } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["recording", id] }),
  });

  const restoreRec = useMutation({
    mutationFn: () => apiClient.post(`/recordings/${id}/restore`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["recording", id] }),
  });

  const createTemplate = useMutation({
    mutationFn: (name: string) =>
      apiClient.post<{ id: number }>(`/templates/from-recording/${id}`, { name }),
    onSuccess: (res) => {
      setCreateTemplateOpen(false);
      setCreateTemplateName("");
      router.push(`/templates/${res.data.id}`);
    },
  });

  const uploadTo = useMutation({
    mutationFn: (platform: string) =>
      apiClient.post(`/recordings/${id}/upload/${platform.toLowerCase()}`),
    onSuccess: () => {
      setUploadError(null);
      qc.invalidateQueries({ queryKey: ["recording", id] });
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setUploadError(msg ?? "Upload failed");
    },
  });

  const STAGE_RERUN_ENDPOINT: Record<string, string> = {
    DOWNLOAD:           `/recordings/${id}/download`,
    TRANSCRIBE:         `/recordings/${id}/transcribe?force=true`,
    EXTRACT_TOPICS:     `/recordings/${id}/topics`,
    GENERATE_SUBTITLES: `/recordings/${id}/subtitles`,
  };

  const [rerunningStage, setRerunningStage] = useState<string | null>(null);

  async function handleStageRerun(stageType: string) {
    const endpoint = STAGE_RERUN_ENDPOINT[normalizeStageType(stageType)];
    if (!endpoint) return;
    setRerunningStage(stageType);
    try {
      await apiClient.post(endpoint);
      qc.invalidateQueries({ queryKey: ["recording", id] });
    } finally {
      setRerunningStage(null);
    }
  }

  const hasProcessedVid = !!recording?.videos?.processed?.exists;
  const hasOriginalVid = !!recording?.videos?.original?.exists;

  const defaultVideoTab: "processed" | "original" =
    !hasProcessedVid && hasOriginalVid ? "original" : "processed";

  const videoTab =
    videoTabChoice !== null &&
    ((videoTabChoice === "processed" && hasProcessedVid) ||
      (videoTabChoice === "original" && hasOriginalVid))
      ? videoTabChoice
      : defaultVideoTab;

  const isActing = run.isPending || pause.isPending || deleteRec.isPending || resetRec.isPending || restoreRec.isPending;
  const isSoftDeleted = !!recording?.soft_deleted_at;

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center p-8">
        <div className="text-sm text-gray-400">Загрузка…</div>
      </div>
    );
  }

  if (error || !recording) {
    return (
      <div className="p-8">
        <p className="text-sm text-red-400">Recording not found</p>
        <Link href="/recordings" className="mt-2 inline-block text-sm text-[#224C87] hover:underline">
          ← Back to recordings
        </Link>
      </div>
    );
  }

  // Topics
  const topicTimestamps: TopicTimestamp[] = (() => {
    if (!recording.topics?.exists || !recording.topics.versions?.length) return [];
    const activeId = recording.topics.active_version;
    const activeVer = activeId
      ? (recording.topics.versions.find((v) => v.id === activeId) ?? recording.topics.versions[0])
      : recording.topics.versions[0];
    return activeVer?.topic_timestamps ?? [];
  })();

  // Pipeline stages: canonical order
  const stageOrderList = CANONICAL_STAGE_ORDER as readonly string[];
  const dbStages = [
    ...stageOrderList
      .map((t) => recording.processing_stages.find((s) => normalizeStageType(s.stage_type) === t))
      .filter(Boolean) as ProcessingStage[],
    ...recording.processing_stages.filter(
      (s) => !stageOrderList.includes(normalizeStageType(s.stage_type))
    ),
  ];

  const hasDownloadStage = dbStages.some((s) => normalizeStageType(s.stage_type) === "DOWNLOAD");
  const ingressLifecycle = deriveIngressLifecycle(recording);
  const syntheticDownload: ProcessingStage | null = !hasDownloadStage
    ? {
        stage_type: "DOWNLOAD",
        status: phaseToStageStatus(ingressLifecycle.phase),
        failed: ingressLifecycle.phase === "failed",
        failed_reason: ingressLifecycle.phase === "failed" ? (ingressLifecycle.hint ?? null) : null,
        started_at: null,
        completed_at: null,
        retry_count: 0,
      }
    : null;

  const allPipelineStages: ProcessingStage[] = [
    ...(syntheticDownload ? [syntheticDownload] : dbStages.filter((s) => normalizeStageType(s.stage_type) === "DOWNLOAD")),
    ...dbStages.filter((s) => normalizeStageType(s.stage_type) !== "DOWNLOAD"),
  ];

  const hasVideoFiles = hasProcessedVid || hasOriginalVid;
  const showMediaSection =
    hasVideoFiles ||
    !!recording.subtitles?.srt?.exists ||
    !!recording.subtitles?.vtt?.exists ||
    !!recording.transcription?.exists;

  async function downloadArtifact(fileType: string, filename: string) {
    setMediaDownloadError(null);
    try {
      const res = await apiClient.get(`/recordings/${id}/files/${fileType}`, { responseType: "blob" });
      const blobUrl = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(blobUrl);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setMediaDownloadError(typeof detail === "string" ? detail : "Не удалось скачать файл");
    }
  }

  const dlStem = `recording-${recording.id}`;

  const templateDetailNavValue = renderRecordingTemplateNavValue(
    recordingConfig
      ? {
          isMapped: recordingConfig.is_mapped,
          templateId: recordingConfig.template_id,
          templateName: recordingConfig.template_name,
        }
      : {
          isMapped: recording.is_mapped,
          templateId: recording.template_id,
          templateName: recording.template_name ?? null,
        }
  );

  return (
    <div className="w-full min-w-0 p-6 sm:p-8">
      {/* ── Header ── */}
      <div className="mb-5 flex flex-wrap items-center gap-4">
        <Link
          href="/recordings"
          className="flex items-center gap-1.5 text-sm text-gray-500 transition-colors hover:text-gray-700"
        >
          <ArrowLeft size={16} />
          Записи
        </Link>
        <span className="text-gray-300">/</span>
        <h1 className="min-w-0 flex-1 truncate text-lg font-semibold text-gray-900">
          {recording.display_name}
        </h1>
        <StatusBadge status={recording.status} failed={recording.failed} />
      </div>

      {/* ── Error banners ── */}
      {recording.failed && recording.failed_reason && (
        <div className="mb-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
          <span className="font-medium">Ошибка:</span> {recording.failed_reason}
        </div>
      )}
      {uploadError && (
        <div className="mb-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
          {uploadError}
        </div>
      )}

      {/* ── 2-column layout ── */}
      <div className="flex flex-col gap-6 lg:flex-row lg:items-start">

        {/* ════ MAIN COLUMN ════ */}
        <div className="min-w-0 flex-1 space-y-6">

          {/* Video */}
          {hasVideoFiles && (
            <div className="rounded-2xl border border-[#D9D9D9] bg-white p-5 shadow-sm">
              <h2 className="mb-4 text-xs font-semibold uppercase tracking-wider text-gray-500">Видео</h2>
              {hasProcessedVid && hasOriginalVid && (
                <div className="mb-3 flex gap-2">
                  <button
                    type="button"
                    onClick={() => setVideoTabChoice("processed")}
                    className={cn(
                      "rounded-xl border px-4 py-2 text-sm font-medium transition-colors",
                      videoTab === "processed"
                        ? "border-[#224C87] bg-[#224C87]/10 text-[#224C87]"
                        : "border-[#D9D9D9] bg-white text-gray-600 hover:bg-gray-50"
                    )}
                  >
                    Обработанное
                  </button>
                  <button
                    type="button"
                    onClick={() => setVideoTabChoice("original")}
                    className={cn(
                      "rounded-xl border px-4 py-2 text-sm font-medium transition-colors",
                      videoTab === "original"
                        ? "border-[#224C87] bg-[#224C87]/10 text-[#224C87]"
                        : "border-[#D9D9D9] bg-white text-gray-600 hover:bg-gray-50"
                    )}
                  >
                    Исходное
                  </button>
                </div>
              )}
              {videoTab === "processed" && hasProcessedVid && (
                <RecordingVideoPlayer
                  key={`${id}-processed`}
                  recordingId={id}
                  variant="processed"
                  sizeLabel={
                    recording.videos?.processed?.size_mb != null
                      ? `${recording.videos.processed.size_mb} МБ`
                      : undefined
                  }
                />
              )}
              {videoTab === "original" && hasOriginalVid && (
                <RecordingVideoPlayer
                  key={`${id}-original`}
                  recordingId={id}
                  variant="original"
                  sizeLabel={
                    recording.videos?.original?.size_mb != null
                      ? `${recording.videos.original.size_mb} МБ`
                      : undefined
                  }
                />
              )}
            </div>
          )}

          {/* Media & Downloads */}
          {showMediaSection && (
            <div className="rounded-2xl border border-[#D9D9D9] bg-white p-5 shadow-sm">
              <h2 className="mb-4 text-xs font-semibold uppercase tracking-wider text-gray-500">
                Файлы и артефакты
              </h2>
              {mediaDownloadError && (
                <div className="mb-3 rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-xs text-red-600">
                  {mediaDownloadError}
                </div>
              )}
              <div className="flex flex-wrap gap-2">
                {recording.subtitles?.srt?.exists && (
                  <button
                    type="button"
                    onClick={() => downloadArtifact("srt", `${dlStem}.srt`)}
                    className="rounded-xl border border-[#D9D9D9] bg-white px-3 py-2 text-xs font-medium transition-colors hover:bg-gray-50"
                  >
                    SRT{recording.subtitles.srt.size_kb != null ? ` (${recording.subtitles.srt.size_kb} КБ)` : ""}
                  </button>
                )}
                {recording.subtitles?.vtt?.exists && (
                  <button
                    type="button"
                    onClick={() => downloadArtifact("vtt", `${dlStem}.vtt`)}
                    className="rounded-xl border border-[#D9D9D9] bg-white px-3 py-2 text-xs font-medium transition-colors hover:bg-gray-50"
                  >
                    VTT{recording.subtitles.vtt.size_kb != null ? ` (${recording.subtitles.vtt.size_kb} КБ)` : ""}
                  </button>
                )}
                {recording.transcription?.exists && (
                  <>
                    <button
                      type="button"
                      onClick={() => downloadArtifact("transcript_json", `${dlStem}_transcript.json`)}
                      className="rounded-xl border border-[#D9D9D9] bg-white px-3 py-2 text-xs font-medium transition-colors hover:bg-gray-50"
                    >
                      Транскрипция JSON
                    </button>
                    <button
                      type="button"
                      onClick={() => downloadArtifact("transcript_txt", `${dlStem}_transcript.txt`)}
                      className="rounded-xl border border-[#D9D9D9] bg-white px-3 py-2 text-xs font-medium transition-colors hover:bg-gray-50"
                    >
                      Транскрипция TXT
                    </button>
                    <button
                      type="button"
                      onClick={() => downloadArtifact("transcript_words", `${dlStem}_words.txt`)}
                      className="rounded-xl border border-[#D9D9D9] bg-white px-3 py-2 text-xs font-medium transition-colors hover:bg-gray-50"
                    >
                      Слова TXT
                    </button>
                  </>
                )}
              </div>
            </div>
          )}

          {/* Topics & Timecodes (collapsible, open by default) */}
          {recording.topics?.exists && (
            <CollapsibleCard title="Темы и таймкоды" defaultOpen={true}>
              {topicTimestamps.length > 0 ? (
                <ol className="space-y-2">
                  {topicTimestamps.map((t, i) => (
                    <li key={i} className="flex items-baseline gap-3">
                      <span className="w-12 shrink-0 font-mono text-xs text-[#224C87]">
                        {formatTimecode(t.start)}
                      </span>
                      <span className="text-sm text-gray-800">{t.topic}</span>
                      {t.end != null && (
                        <span className="ml-auto shrink-0 font-mono text-[11px] text-gray-300">
                          → {formatTimecode(t.end)}
                        </span>
                      )}
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="text-sm text-gray-400">Топики ещё не извлечены</p>
              )}
            </CollapsibleCard>
          )}

          {/* Config (collapsible) */}
          <CollapsibleCard title="Конфигурация">
            {configLoading ? (
              <div className="flex items-center gap-2 text-sm text-gray-400">
                <Loader2 size={14} className="animate-spin" />
                Загрузка…
              </div>
            ) : !recordingConfig ? (
              <p className="text-sm text-gray-400">Нет данных</p>
            ) : (
              <dl className="space-y-3">
                <ConfigRow
                  label="Шаблон"
                  value={renderRecordingTemplateNavValue({
                    isMapped: recordingConfig.is_mapped,
                    templateId: recordingConfig.template_id,
                    templateName: recordingConfig.template_name,
                  })}
                />
                {recordingConfig.has_manual_override && (
                  <ConfigRow label="Переопределение" value="Есть ручной override" highlight />
                )}
                {recordingConfig.processing_config?.transcription && (() => {
                  const t = recordingConfig.processing_config!.transcription!;
                  return (
                    <>
                      {t.language     && <ConfigRow label="Язык"          value={t.language} />}
                      {t.granularity  && <ConfigRow label="Гранулярность" value={t.granularity} />}
                      {t.enable_transcription != null && <ConfigRow label="Транскрипция" value={t.enable_transcription ? "Вкл" : "Выкл"} />}
                      {t.enable_topics    != null && <ConfigRow label="Темы"          value={t.enable_topics    ? "Вкл" : "Выкл"} />}
                      {t.enable_subtitles != null && <ConfigRow label="Субтитры"      value={t.enable_subtitles ? "Вкл" : "Выкл"} />}
                    </>
                  );
                })()}
                {recordingConfig.output_config && (() => {
                  const o = recordingConfig.output_config!;
                  return (
                    <>
                      {o.auto_upload    != null && <ConfigRow label="Авто-загрузка"      value={o.auto_upload    ? "Вкл" : "Выкл"} />}
                      {o.upload_captions != null && <ConfigRow label="Загрузка субтитров" value={o.upload_captions ? "Вкл" : "Выкл"} />}
                      {o.preset_ids?.length      ? <ConfigRow label="Пресеты"            value={o.preset_ids.join(", ")} /> : null}
                    </>
                  );
                })()}
                {recordingConfig.metadata_config && (() => {
                  const m = recordingConfig.metadata_config!;
                  return (
                    <>
                      {m.title_template       && <ConfigRow label="Title template"       value={m.title_template}       mono />}
                      {m.description_template && <ConfigRow label="Description template" value={m.description_template} mono />}
                    </>
                  );
                })()}
              </dl>
            )}
          </CollapsibleCard>

          {/* Details (collapsible, default closed) */}
          <CollapsibleCard title="Подробнее">
            <dl className="space-y-2.5">
              <InfoRow label="ID"           value={`#${recording.id}`} />
              <InfoRow label="Название"     value={recording.display_name} />
              <InfoRow label="Статус"       value={recording.status} />
              {recording.source?.source_type && <InfoRow label="Источник" value={recording.source.source_type} />}
              <InfoRow label="Дата"         value={formatDate(recording.start_time)} />
              <InfoRow label="Длительность" value={formatDuration(recording.duration)} />
              {recording.video_file_size && <InfoRow label="Размер файла" value={formatFileSize(recording.video_file_size)} />}
              {recording.pipeline_duration_seconds ? <InfoRow label="Время пайплайна" value={`${Math.round(recording.pipeline_duration_seconds)} с`} /> : null}
              <InfoRow label="Шаблон" value={templateDetailNavValue} />
            </dl>
          </CollapsibleCard>
        </div>

        {/* ════ SIDEBAR ════ */}
        <div className="w-full space-y-5 lg:w-80 lg:shrink-0">

          {/* Control Panel */}
          <div className="rounded-2xl border border-[#D9D9D9] bg-white p-4 shadow-sm">
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-500">Управление</h2>
            <div className="space-y-2">
              {isSoftDeleted ? (
                <button
                  disabled={isActing}
                  onClick={() => restoreRec.mutate()}
                  className="flex w-full items-center justify-center gap-2 rounded-xl bg-green-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-green-700 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {restoreRec.isPending ? <Loader2 size={15} className="animate-spin" /> : <ArchiveRestore size={15} />}
                  Восстановить
                </button>
              ) : (
                <>
                  <button
                    disabled={!recording.can_run || isActing}
                    onClick={() => run.mutate()}
                    className="flex w-full items-center justify-center gap-2 rounded-xl bg-[#224C87] px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[#1a3d6e] disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {run.isPending ? <Loader2 size={15} className="animate-spin" /> : <Play size={15} />}
                    Запустить
                  </button>
                  <button
                    disabled={!recording.can_run || isActing}
                    onClick={() => setRunConfigOpen(true)}
                    className="flex w-full items-center justify-center gap-2 rounded-xl border border-[#224C87]/30 bg-white px-4 py-2 text-sm font-medium text-[#224C87] transition-colors hover:bg-[#224C87]/5 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <Settings2 size={14} />
                    С конфигурацией…
                  </button>
                </>
              )}
              <div className="flex gap-2 pt-1">
                {!isSoftDeleted && (
                  <>
                    <button
                      disabled={!recording.can_pause || isActing}
                      onClick={() => pause.mutate()}
                      className="flex flex-1 items-center justify-center gap-1.5 rounded-xl border border-[#D9D9D9] bg-white px-3 py-2 text-sm font-medium transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      {pause.isPending ? <Loader2 size={13} className="animate-spin" /> : <Pause size={13} />}
                      Пауза
                    </button>
                    <button
                      disabled={isActing}
                      onClick={() => setResetConfirm(true)}
                      className="flex flex-1 items-center justify-center gap-1.5 rounded-xl border border-[#D9D9D9] bg-white px-3 py-2 text-sm font-medium transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      {resetRec.isPending ? <Loader2 size={13} className="animate-spin" /> : <RotateCcw size={13} />}
                      Сброс
                    </button>
                  </>
                )}
                <button
                  disabled={isActing}
                  onClick={() => setDeleteConfirm(true)}
                  title="Удалить"
                  className="flex items-center justify-center rounded-xl border border-red-200 bg-white px-3 py-2 text-sm font-medium text-red-500 transition-colors hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <Trash2 size={13} />
                </button>
              </div>
              <button
                onClick={() => { setCreateTemplateName(recording.display_name); setCreateTemplateOpen(true); }}
                className="flex w-full items-center justify-center gap-1.5 rounded-xl border border-[#D9D9D9] bg-white px-3 py-2 text-sm font-medium text-gray-600 transition-colors hover:border-[#224C87]/40 hover:bg-[#224C87]/5 hover:text-[#224C87]"
              >
                <FilePlus2 size={13} />
                Создать шаблон
              </button>
            </div>
          </div>

          {/* Pipeline */}
          <div className="rounded-2xl border border-[#D9D9D9] bg-white p-4 shadow-sm">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500">Пайплайн</h2>
              {recording.pipeline_duration_seconds != null && recording.pipeline_duration_seconds > 0 && (
                <span className="text-[10px] text-gray-400">
                  ~{Math.round(recording.pipeline_duration_seconds)} с
                </span>
              )}
            </div>
            {allPipelineStages.length === 0 ? (
              <p className="text-xs text-gray-400">Нет данных</p>
            ) : (
              <div className="divide-y divide-[#F5F5F5]">
                {allPipelineStages.map((s) => {
                  const canon = normalizeStageType(s.stage_type);
                  const canRerun = !!STAGE_RERUN_ENDPOINT[canon] &&
                    !["PENDING", "IN_PROGRESS"].includes(s.failed ? "FAILED" : s.status.toUpperCase());
                  const isRerunning = rerunningStage === s.stage_type;
                  return (
                    <div key={canon} className="flex items-center gap-1">
                      <div className="flex-1 min-w-0">
                        <PipelineCompactRow stage={s} />
                      </div>
                      {canRerun && (
                        <button
                          type="button"
                          title="Перезапустить этап"
                          disabled={isRerunning || !!rerunningStage}
                          onClick={() => handleStageRerun(s.stage_type)}
                          className="shrink-0 rounded-lg border border-[#D9D9D9] bg-white p-1 text-gray-400 transition-colors hover:border-[#224C87] hover:bg-[#224C87]/5 hover:text-[#224C87] disabled:opacity-40"
                        >
                          {isRerunning
                            ? <Loader2 size={11} className="animate-spin" />
                            : <RotateCcw size={11} />}
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Publications */}
          <div className="rounded-2xl border border-[#D9D9D9] bg-white p-4 shadow-sm">
            <div className="mb-1 flex items-center justify-between">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500">Публикации</h2>
              {recording.upload_summary && recording.upload_summary.total > 0 && (
                <span className={cn(
                  "rounded-full px-2 py-0.5 text-[10px] font-medium",
                  recording.upload_summary.uploaded === recording.upload_summary.total
                    ? "bg-green-50 text-green-700"
                    : recording.upload_summary.failed > 0
                      ? "bg-red-50 text-red-600"
                      : "bg-gray-100 text-gray-500"
                )}>
                  {recording.upload_summary.uploaded}/{recording.upload_summary.total}
                </span>
              )}
            </div>
            {recording.outputs.length === 0 ? (
              <p className="mt-2 text-xs text-gray-400">
                Платформы не настроены. Добавьте пресеты и запустите запись.
              </p>
            ) : (
              <div className="divide-y divide-[#F5F5F5]">
                {recording.outputs.map((output) => (
                  <PlatformOutputRow
                    key={output.id}
                    output={output}
                    readyToUpload={recording.ready_to_upload}
                    onUpload={(targetType) => uploadTo.mutate(targetType)}
                    uploadPending={uploadTo.isPending}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Info */}
          <div className="rounded-2xl border border-[#D9D9D9] bg-white p-4 shadow-sm">
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-500">Инфо</h2>
            <dl className="space-y-2">
              <SidebarInfoRow label="ID"          value={`#${recording.id}`} />
              <SidebarInfoRow label="Шаблон" value={templateDetailNavValue} />
              <SidebarInfoRow label="Дата"        value={formatDate(recording.start_time)} />
              {recording.duration > 0 && (
                <SidebarInfoRow label="Длительность" value={formatDuration(recording.duration)} />
              )}
              {recording.video_file_size ? (
                <SidebarInfoRow label="Размер" value={formatFileSize(recording.video_file_size)} />
              ) : null}
              {recording.pipeline_duration_seconds ? (
                <SidebarInfoRow label="Пайплайн" value={`${Math.round(recording.pipeline_duration_seconds)} с`} />
              ) : null}
            </dl>
          </div>
        </div>
      </div>

      <ConfirmDialog
        open={deleteConfirm}
        title="Удалить запись?"
        description={`"${recording.display_name}" будет удалена (soft-delete, восстановима в течение ограниченного времени).`}
        confirmLabel="Удалить"
        cancelLabel="Отмена"
        danger
        onConfirm={() => { setDeleteConfirm(false); deleteRec.mutate(); }}
        onCancel={() => setDeleteConfirm(false)}
      />

      <ConfirmDialog
        open={resetConfirm}
        title="Сбросить запись?"
        description="Запись вернётся в статус INITIALIZED."
        confirmLabel="Сбросить"
        cancelLabel="Отмена"
        onConfirm={() => { setResetConfirm(false); resetRec.mutate(); }}
        onCancel={() => setResetConfirm(false)}
      >
        <label className="flex items-center gap-2 text-sm text-gray-700 select-none cursor-pointer">
          <input
            type="checkbox"
            checked={resetDeleteFiles}
            onChange={(e) => setResetDeleteFiles(e.target.checked)}
            className="rounded border-gray-300 text-[#224C87] focus:ring-[#224C87]/30"
          />
          Удалить обработанные файлы (видео, аудио, транскрипция)
        </label>
      </ConfirmDialog>

      <RunConfigModal
        open={runConfigOpen}
        onClose={() => setRunConfigOpen(false)}
        mode="single"
        recordingId={Number(id)}
        recordingName={recording.display_name}
        onSuccess={() => qc.invalidateQueries({ queryKey: ["recording", id] })}
      />

      {/* Create template modal */}
      {createTemplateOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
          onClick={(e) => { if (e.currentTarget === e.target) { setCreateTemplateOpen(false); } }}
        >
          <div className="w-full max-w-sm rounded-2xl bg-white p-6 shadow-xl">
            <h2 className="mb-4 text-sm font-semibold text-gray-900">Создать шаблон из записи</h2>
            <div className="space-y-3">
              <div className="space-y-1">
                <label className="text-xs font-medium text-gray-500">Название шаблона</label>
                <input
                  type="text"
                  autoFocus
                  value={createTemplateName}
                  onChange={(e) => setCreateTemplateName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && createTemplateName.trim()) createTemplate.mutate(createTemplateName.trim());
                    if (e.key === "Escape") setCreateTemplateOpen(false);
                  }}
                  placeholder="Название шаблона"
                  className="w-full rounded-xl border border-[#D9D9D9] px-3 py-2 text-sm outline-none focus:border-[#224C87] focus:ring-1 focus:ring-[#224C87]/20"
                />
              </div>
              {createTemplate.isError && (
                <p className="text-xs text-red-500">
                  {(createTemplate.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Ошибка"}
                </p>
              )}
              <div className="flex justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => setCreateTemplateOpen(false)}
                  className="rounded-xl border border-[#D9D9D9] px-4 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50"
                >
                  Отмена
                </button>
                <button
                  type="button"
                  disabled={!createTemplateName.trim() || createTemplate.isPending}
                  onClick={() => createTemplate.mutate(createTemplateName.trim())}
                  className="flex items-center gap-1.5 rounded-xl bg-[#224C87] px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-[#1a3d6e] disabled:opacity-50"
                >
                  {createTemplate.isPending ? <Loader2 size={14} className="animate-spin" /> : <FilePlus2 size={14} />}
                  Создать
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helper row components
// ---------------------------------------------------------------------------

function InfoRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="shrink-0 text-sm text-gray-500">{label}</dt>
      <dd className="min-w-0 max-w-[65%] text-right text-sm text-gray-900">{value}</dd>
    </div>
  );
}

function SidebarInfoRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex justify-between gap-2">
      <dt className="shrink-0 text-[11px] text-gray-500">{label}</dt>
      <dd
        className="min-w-0 truncate text-right text-[11px] font-medium text-gray-800"
        title={typeof value === "string" ? value : undefined}
      >
        {value}
      </dd>
    </div>
  );
}

function ConfigRow({
  label,
  value,
  mono,
  highlight,
}: {
  label: string;
  value: ReactNode;
  mono?: boolean;
  highlight?: boolean;
}) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="shrink-0 text-sm text-gray-500">{label}</dt>
      <dd
        className={cn(
          "min-w-0 max-w-[70%] text-right text-sm",
          highlight ? "font-medium text-amber-600" : "text-gray-900",
          mono && "font-mono text-xs"
        )}
      >
        {value}
      </dd>
    </div>
  );
}
