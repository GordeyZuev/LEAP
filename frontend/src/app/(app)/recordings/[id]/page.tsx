"use client";

import { use, useEffect, useRef, useState, type ComponentType } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft, Play, Pause, Trash2, Upload, ExternalLink,
  CheckCircle2, XCircle, Clock, Loader2, SkipForward, RotateCcw, Settings2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/api/client";
import { StatusBadge, type ProcessingStatus } from "@/components/ui/status-badge";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { RunConfigModal } from "@/components/recordings/run-config-modal";

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
  pipeline_duration_seconds: number | null;
  is_mapped: boolean;
  template_id: number | null;
  video_file_size: number | null;
  created_at: string;
  can_run: boolean;
  can_pause: boolean;
  ready_to_upload: boolean;
  topics?: TopicsData;
  videos?: Record<string, VideoVariantInfo> | null;
  subtitles?: Record<string, SubtitleVariantInfo> | null;
  transcription?: TranscriptionDetail | null;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
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
  if (!startedAt || !completedAt) return "—";
  const ms = new Date(completedAt).getTime() - new Date(startedAt).getTime();
  if (!Number.isFinite(ms) || ms < 0) return "—";
  const secTotal = Math.floor(ms / 1000);
  const h = Math.floor(secTotal / 3600);
  const m = Math.floor((secTotal % 3600) / 60);
  const s = secTotal % 60;
  if (h > 0) return `${h} ч ${m} мин ${s} с`;
  if (m > 0) return `${m} мин ${s} с`;
  return `${s} с`;
}

function formatDateTimeShort(iso: string): string {
  return new Date(iso).toLocaleString("ru-RU", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
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

const STAGE_META: Record<string, { name: string; description: string }> = {
  DOWNLOAD: { name: "Получение файла", description: "Загрузка медиа из источника" },
  TRIM: { name: "Обрезка тишины", description: "Удаление тишины в начале и конце (FFmpeg)" },
  TRANSCRIBE: { name: "Транскрипция", description: "Распознавание речи (ASR)" },
  EXTRACT_TOPICS: { name: "Извлечение тем", description: "Тематический разбор (DeepSeek)" },
  GENERATE_SUBTITLES: { name: "Субтитры", description: "Генерация SRT и VTT" },
  UPLOAD: { name: "Публикация на платформы", description: "Выгрузка на внешние платформы" },
};

type LifecyclePhase = "pending" | "active" | "done" | "failed" | "skipped";

function phaseToStageStatus(phase: LifecyclePhase): string {
  switch (phase) {
    case "done": return "COMPLETED";
    case "active": return "IN_PROGRESS";
    case "failed": return "FAILED";
    case "skipped": return "SKIPPED";
    default: return "PENDING";
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


const STAGE_STATUS_CONFIG: Record<string, { icon: ComponentType<{ size?: number; className?: string }>; className: string }> = {
  COMPLETED:   { icon: CheckCircle2, className: "text-green-500 bg-green-50 border-green-200" },
  FAILED:      { icon: XCircle,      className: "text-red-500 bg-red-50 border-red-200" },
  IN_PROGRESS: { icon: Loader2,      className: "text-blue-500 bg-blue-50 border-blue-200 animate-pulse" },
  SKIPPED:     { icon: SkipForward,  className: "text-gray-400 bg-gray-50 border-gray-200" },
  PENDING:     { icon: Clock,        className: "text-gray-400 bg-gray-50 border-gray-200" },
};

const TARGET_LABELS: Record<string, string> = {
  YOUTUBE:      "YouTube",
  VK:           "VK",
  YANDEX_DISK:  "Yandex Disk",
};

const PLATFORM_STATUS_CONFIG: Record<string, { icon: ComponentType<{ size?: number; className?: string }>; className: string; label: string }> = {
  UPLOADED:     { icon: CheckCircle2, className: "text-green-500 bg-green-50 border-green-200", label: "Uploaded" },
  UPLOADING:    { icon: Loader2,      className: "text-blue-500 bg-blue-50 border-blue-200",    label: "Uploading…" },
  FAILED:       { icon: XCircle,      className: "text-red-500 bg-red-50 border-red-200",       label: "Failed" },
  NOT_UPLOADED: { icon: Clock,        className: "text-gray-400 bg-gray-50 border-gray-200",    label: "Not uploaded" },
};

const ACTIVE_DETAIL_POLL = new Set<string>(["DOWNLOADING", "PROCESSING", "UPLOADING"]);

// ---------------------------------------------------------------------------
// PipelineCompactRow
// ---------------------------------------------------------------------------

function PipelineCompactRow({ stage }: { stage: ProcessingStage }) {
  const canon = normalizeStageType(stage.stage_type);
  const status = stage.failed ? "FAILED" : stage.status.toUpperCase();
  const cfg = STAGE_STATUS_CONFIG[status] ?? STAGE_STATUS_CONFIG["PENDING"];
  const Icon = cfg.icon;
  const meta = STAGE_META[canon];
  const title = meta?.name ?? stage.stage_type;
  const description = meta?.description ?? "";

  const durationLabel = formatStageDuration(stage.started_at, stage.completed_at);
  const windowLabel =
    stage.started_at && stage.completed_at
      ? `${formatDateTimeShort(stage.started_at)} → ${formatDateTimeShort(stage.completed_at)}`
      : stage.started_at
        ? `${formatDateTimeShort(stage.started_at)} → …`
        : "—";

  return (
    <div className="flex items-start gap-2 py-2.5">
      <div
        className={cn(
          "flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border",
          cfg.className
        )}
      >
        <Icon size={14} className={status === "IN_PROGRESS" ? "animate-spin" : ""} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-2">
          <span className="text-xs font-semibold text-gray-900">{title}</span>
          <span className="text-[10px] uppercase tracking-wide text-gray-400">{stage.status}</span>
        </div>
        {description ? (
          <p className="truncate text-[11px] text-gray-500" title={description}>{description}</p>
        ) : null}
        {stage.retry_count > 0 ? (
          <p className="text-[11px] text-amber-700">Повторов: {stage.retry_count}</p>
        ) : null}
        {stage.failed_reason ? (
          <p className="break-words text-[11px] text-red-600">{stage.failed_reason}</p>
        ) : null}
      </div>
      <div className="shrink-0 text-right text-[10px] tabular-nums leading-snug text-gray-600">
        <div>{durationLabel}</div>
        <div className="max-w-[min(22rem,45vw)] truncate text-gray-400" title={windowLabel}>
          {windowLabel}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// PipelineSectionDivider — visual separator between pipeline blocks
// ---------------------------------------------------------------------------

function PipelineSectionDivider() {
  return <div className="my-1.5 border-t border-dashed border-[#E8E8E8]" />;
}

// ---------------------------------------------------------------------------
// PlatformOutputRow — one row per upload target, styled like PipelineCompactRow
// ---------------------------------------------------------------------------

function PlatformOutputRow({
  output,
  readyToUpload,
  onUpload,
  uploadPending,
}: {
  output: OutputTarget | null;
  readyToUpload: boolean;
  onUpload: (targetType: string) => void;
  uploadPending: boolean;
}) {
  if (!output) {
    const cfg = STAGE_STATUS_CONFIG["PENDING"];
    const Icon = cfg.icon;
    return (
      <div className="flex items-start gap-2 py-2.5">
        <div className={cn("flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border", cfg.className)}>
          <Icon size={14} />
        </div>
        <div className="min-w-0 flex-1">
          <span className="text-xs font-semibold text-gray-900">Публикация на платформы</span>
          <p className="text-[11px] text-gray-400">Платформы не настроены</p>
        </div>
      </div>
    );
  }

  const ostatus = output.failed ? "FAILED" : output.status;
  const cfg = PLATFORM_STATUS_CONFIG[ostatus] ?? PLATFORM_STATUS_CONFIG["NOT_UPLOADED"];
  const Icon = cfg.icon;
  const label = TARGET_LABELS[output.target_type] ?? output.target_type;
  const url = output.target_meta?.video_url as string | undefined;
  const canUpload = readyToUpload && output.status === "NOT_UPLOADED";

  return (
    <div className="flex items-start gap-2 py-2.5">
      <div className={cn("flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border", cfg.className)}>
        <Icon size={14} className={ostatus === "UPLOADING" ? "animate-spin" : ""} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-2">
          <span className="text-xs font-semibold text-gray-900">{label}</span>
          <span className="text-[10px] uppercase tracking-wide text-gray-400">{cfg.label}</span>
          {output.preset && (
            <span className="text-[11px] text-gray-400">({output.preset.name})</span>
          )}
        </div>
        {output.failed_reason ? (
          <p className="break-words text-[11px] text-red-600">{output.failed_reason}</p>
        ) : null}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {output.uploaded_at ? (
          <span className="text-[10px] tabular-nums text-gray-400">
            {formatDateTimeShort(output.uploaded_at)}
          </span>
        ) : null}
        {url && output.status === "UPLOADED" ? (
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-0.5 text-[11px] text-[#224C87] hover:underline"
          >
            View <ExternalLink size={10} />
          </a>
        ) : null}
        {(canUpload || output.status === "FAILED") ? (
          <button
            type="button"
            onClick={() => onUpload(output.target_type)}
            disabled={uploadPending}
            className="flex items-center gap-1 rounded-lg border border-[#D9D9D9] bg-white px-2 py-0.5 text-[11px] font-medium transition-colors hover:border-[#224C87] hover:bg-[#224C87] hover:text-white disabled:opacity-40"
          >
            <Upload size={10} />
            {output.status === "FAILED" ? "Retry" : "Upload"}
          </button>
        ) : null}
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
  const blobUrlRef = useRef<string | null>(null);

  useEffect(() => {
    return () => {
      if (blobUrlRef.current) URL.revokeObjectURL(blobUrlRef.current);
    };
  }, []);

  function loadVideo() {
    setLoading(true);
    setLoadError(null);
    setProgress(0);

    void apiClient
      .get(`/recordings/${recordingId}/media?type=${variant}`, {
        responseType: "blob",
        onDownloadProgress: (e) => {
          if (e.total) setProgress(Math.round((e.loaded / e.total) * 100));
        },
      })
      .then((res) => {
        const url = URL.createObjectURL(res.data as Blob);
        blobUrlRef.current = url;
        setSrc(url);
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
// Main page
// ---------------------------------------------------------------------------

export default function RecordingDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const qc = useQueryClient();
  const [videoTabChoice, setVideoTabChoice] = useState<"processed" | "original" | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [resetConfirm, setResetConfirm] = useState(false);
  const [runConfigOpen, setRunConfigOpen] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [mediaDownloadError, setMediaDownloadError] = useState<string | null>(null);

  const { data: recording, isLoading, error } = useQuery<RecordingDetail>({
    queryKey: ["recording", id],
    queryFn: async () => {
      const res = await apiClient.get<RecordingDetail>(`/recordings/${id}?detailed=true`);
      return res.data;
    },
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s && ACTIVE_DETAIL_POLL.has(s) ? 3000 : false;
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
    mutationFn: () => apiClient.post(`/recordings/${id}/reset`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["recording", id] }),
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

  const isActing = run.isPending || pause.isPending || deleteRec.isPending || resetRec.isPending;

  if (isLoading) {
    return (
      <div className="p-8 flex items-center justify-center h-full">
        <div className="text-sm text-gray-400">Loading…</div>
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

  // Synthesize a DOWNLOAD stage if not in DB (e.g. already-on-disk recordings)
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

  // Split DB stages into ingress (DOWNLOAD) and processing groups
  const ingressStages: ProcessingStage[] = syntheticDownload
    ? [syntheticDownload]
    : dbStages.filter((s) => normalizeStageType(s.stage_type) === "DOWNLOAD");
  const processingStages = dbStages.filter(
    (s) => normalizeStageType(s.stage_type) !== "DOWNLOAD"
  );

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

  return (
    <div className="w-full min-w-0 p-6 sm:p-8">
      {/* Header */}
      <div className="mb-6 flex flex-wrap items-center gap-4">
        <Link
          href="/recordings"
          className="flex items-center gap-1.5 text-sm text-gray-500 transition-colors hover:text-gray-700"
        >
          <ArrowLeft size={16} />
          Recordings
        </Link>
        <span className="text-gray-300">/</span>
        <h1 className="min-w-0 flex-1 truncate text-lg font-semibold text-gray-900">
          {recording.display_name}
        </h1>
        <StatusBadge status={recording.status} failed={recording.failed} />

        <div className="flex flex-wrap items-center gap-2">
          <button
            disabled={!recording.can_run || isActing}
            onClick={() => run.mutate()}
            className="flex items-center gap-1.5 rounded-xl border border-[#D9D9D9] bg-white px-3 py-2 text-sm font-medium transition-colors hover:border-[#224C87] hover:bg-[#224C87] hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
          >
            {run.isPending ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
            Run
          </button>
          <button
            disabled={!recording.can_run || isActing}
            onClick={() => setRunConfigOpen(true)}
            className="flex items-center gap-1.5 rounded-xl border border-[#224C87]/30 bg-white px-3 py-2 text-sm font-medium text-[#224C87] transition-colors hover:bg-[#224C87]/5 disabled:cursor-not-allowed disabled:opacity-40"
            title="Run with custom config override"
          >
            <Settings2 size={14} />
            Run with config…
          </button>
          <button
            disabled={!recording.can_pause || isActing}
            onClick={() => pause.mutate()}
            className="flex items-center gap-1.5 rounded-xl border border-[#D9D9D9] bg-white px-3 py-2 text-sm font-medium transition-colors hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {pause.isPending ? <Loader2 size={14} className="animate-spin" /> : <Pause size={14} />}
            Pause
          </button>
          <button
            onClick={() => setResetConfirm(true)}
            disabled={isActing}
            className="flex items-center gap-1.5 rounded-xl border border-[#D9D9D9] bg-white px-3 py-2 text-sm font-medium transition-colors hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {resetRec.isPending ? <Loader2 size={14} className="animate-spin" /> : <RotateCcw size={14} />}
            Reset
          </button>
          <button
            onClick={() => setDeleteConfirm(true)}
            disabled={isActing}
            className="flex items-center gap-1.5 rounded-xl border border-red-200 bg-white px-3 py-2 text-sm font-medium text-red-500 transition-colors hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Trash2 size={14} />
            Delete
          </button>
        </div>
      </div>

      {/* Error banners */}
      {recording.failed && recording.failed_reason && (
        <div className="mb-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
          <span className="font-medium">Failed:</span> {recording.failed_reason}
        </div>
      )}
      {uploadError && (
        <div className="mb-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
          {uploadError}
        </div>
      )}

      {/* ── Pipeline (all stages unified) ── */}
      <div className="mb-6 rounded-2xl border border-[#D9D9D9] bg-white p-5 shadow-sm">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-[11px] font-semibold uppercase tracking-wider text-gray-500">Пайплайн</h2>
          {recording.pipeline_duration_seconds != null && recording.pipeline_duration_seconds > 0 ? (
            <span className="text-[11px] text-gray-400">
              ~{Math.round(recording.pipeline_duration_seconds)} с
            </span>
          ) : null}
        </div>

        <div>
          {/* Block 1: ingress (DOWNLOAD) */}
          {ingressStages.length > 0 && (
            <div className="divide-y divide-[#F0F0F0]">
              {ingressStages.map((s) => (
                <PipelineCompactRow key={normalizeStageType(s.stage_type)} stage={s} />
              ))}
            </div>
          )}

          {/* Section divider before processing block */}
          {ingressStages.length > 0 && processingStages.length > 0 && (
            <PipelineSectionDivider />
          )}

          {/* Block 2: processing stages */}
          {processingStages.length > 0 && (
            <div className="divide-y divide-[#F0F0F0]">
              {processingStages.map((s) => (
                <PipelineCompactRow key={normalizeStageType(s.stage_type)} stage={s} />
              ))}
            </div>
          )}

          {/* Section divider before upload block */}
          <PipelineSectionDivider />

          {/* Block 3: per-platform upload rows */}
          {recording.outputs.length === 0 ? (
            <PlatformOutputRow
              output={null}
              readyToUpload={false}
              onUpload={() => {}}
              uploadPending={false}
            />
          ) : (
            <div className="divide-y divide-[#F0F0F0]">
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
      </div>

      {/* ── Media & downloads ── */}
      {showMediaSection && (
        <div className="mb-6 rounded-2xl border border-[#D9D9D9] bg-white p-5 shadow-sm">
          <h2 className="mb-4 text-xs font-semibold uppercase tracking-wider text-gray-500">
            Медиа и файлы
          </h2>

          {mediaDownloadError ? (
            <div className="mb-3 rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-xs text-red-600">
              {mediaDownloadError}
            </div>
          ) : null}

          {hasVideoFiles ? (
            <div className="mb-6">
              {hasProcessedVid && hasOriginalVid ? (
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
              ) : null}
              {videoTab === "processed" && hasProcessedVid ? (
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
              ) : null}
              {videoTab === "original" && hasOriginalVid ? (
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
              ) : null}
            </div>
          ) : null}

          <div className="flex flex-wrap gap-2">
            {recording.subtitles?.srt?.exists ? (
              <button
                type="button"
                onClick={() => downloadArtifact("srt", `${dlStem}.srt`)}
                className="rounded-xl border border-[#D9D9D9] bg-white px-3 py-2 text-xs font-medium transition-colors hover:bg-gray-50"
              >
                SRT{recording.subtitles.srt.size_kb != null ? ` (${recording.subtitles.srt.size_kb} КБ)` : ""}
              </button>
            ) : null}
            {recording.subtitles?.vtt?.exists ? (
              <button
                type="button"
                onClick={() => downloadArtifact("vtt", `${dlStem}.vtt`)}
                className="rounded-xl border border-[#D9D9D9] bg-white px-3 py-2 text-xs font-medium transition-colors hover:bg-gray-50"
              >
                VTT{recording.subtitles.vtt.size_kb != null ? ` (${recording.subtitles.vtt.size_kb} КБ)` : ""}
              </button>
            ) : null}
            {recording.transcription?.exists ? (
              <>
                <button
                  type="button"
                  onClick={() => downloadArtifact("transcript_json", `${dlStem}_transcript.json`)}
                  className="rounded-xl border border-[#D9D9D9] bg-white px-3 py-2 text-xs font-medium transition-colors hover:bg-gray-50"
                >
                  JSON транскрипция
                </button>
                <button
                  type="button"
                  onClick={() => downloadArtifact("transcript_txt", `${dlStem}_transcript.txt`)}
                  className="rounded-xl border border-[#D9D9D9] bg-white px-3 py-2 text-xs font-medium transition-colors hover:bg-gray-50"
                >
                  TXT транскрипция
                </button>
                <button
                  type="button"
                  onClick={() => downloadArtifact("transcript_words", `${dlStem}_words.txt`)}
                  className="rounded-xl border border-[#D9D9D9] bg-white px-3 py-2 text-xs font-medium transition-colors hover:bg-gray-50"
                >
                  Слова (TXT)
                </button>
              </>
            ) : null}
          </div>
        </div>
      )}

      {/* ── Topics & Timecodes ── */}
      {recording.topics?.exists ? (
        <div className="mb-6 rounded-2xl border border-[#D9D9D9] bg-white p-5 shadow-sm">
          <h2 className="mb-4 text-xs font-semibold uppercase tracking-wider text-gray-500">
            Topics &amp; Timecodes
          </h2>
          {topicTimestamps.length > 0 ? (
            <ol className="space-y-2">
              {topicTimestamps.map((t, i) => (
                <li key={i} className="flex items-baseline gap-3">
                  <span className="w-12 shrink-0 font-mono text-xs text-gray-400">
                    {formatTimecode(t.start)}
                  </span>
                  <span className="text-sm text-gray-700">{t.topic}</span>
                  {t.end != null ? (
                    <span className="ml-auto shrink-0 font-mono text-[11px] text-gray-300">
                      → {formatTimecode(t.end)}
                    </span>
                  ) : null}
                </li>
              ))}
            </ol>
          ) : (
            <p className="text-sm text-gray-400">Топики ещё не извлечены</p>
          )}
        </div>
      ) : null}

      {/* ── Metadata (Info) — at bottom ── */}
      <div className="rounded-2xl border border-[#D9D9D9] bg-white p-5 shadow-sm">
        <h2 className="mb-4 text-xs font-semibold uppercase tracking-wider text-gray-500">Метаданные</h2>
        <dl className="space-y-2.5">
          <InfoRow label="Название" value={recording.display_name} />
          <InfoRow label="ID" value={`#${recording.id}`} />
          <InfoRow label="Источник" value={recording.source?.source_type ?? "—"} />
          {recording.source?.source_key ? (
            <InfoRow label="Source key" value={recording.source.source_key} />
          ) : null}
          <InfoRow label="Длительность" value={formatDuration(recording.duration)} />
          <InfoRow label="Дата" value={formatDate(recording.start_time)} />
          <InfoRow label="Создано" value={formatDate(recording.created_at)} />
          {recording.video_file_size ? (
            <InfoRow label="Размер файла" value={formatFileSize(recording.video_file_size)} />
          ) : null}
          {recording.pipeline_duration_seconds ? (
            <InfoRow
              label="Время пайплайна"
              value={`${Math.round(recording.pipeline_duration_seconds)} с`}
            />
          ) : null}
          <InfoRow label="Шаблон" value={recording.is_mapped ? `#${recording.template_id}` : "Не привязан"} />
          <InfoRow label="Статус" value={recording.status} />
        </dl>
      </div>

      <ConfirmDialog
        open={deleteConfirm}
        title="Delete recording?"
        description={`"${recording.display_name}" will be soft-deleted and can be restored for a limited time.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        danger
        onConfirm={() => { setDeleteConfirm(false); deleteRec.mutate(); }}
        onCancel={() => setDeleteConfirm(false)}
      />

      <ConfirmDialog
        open={resetConfirm}
        title="Reset recording?"
        description="All processed files (video, audio, transcription) will be deleted and the recording will return to INITIALIZED status. This cannot be undone."
        confirmLabel="Reset"
        cancelLabel="Cancel"
        onConfirm={() => { setResetConfirm(false); resetRec.mutate(); }}
        onCancel={() => setResetConfirm(false)}
      />

      <RunConfigModal
        open={runConfigOpen}
        onClose={() => setRunConfigOpen(false)}
        mode="single"
        recordingId={Number(id)}
        recordingName={recording.display_name}
        onSuccess={() => qc.invalidateQueries({ queryKey: ["recording", id] })}
      />
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="shrink-0 text-sm text-gray-500">{label}</dt>
      <dd className="text-right text-sm text-gray-900">{value}</dd>
    </div>
  );
}
