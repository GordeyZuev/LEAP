"use client";

import { use, useState, useRef, useEffect, useCallback, useMemo, forwardRef, type ComponentType, type ReactNode } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft, Play, Pause, Trash2, Upload, ExternalLink,
  CheckCircle2, XCircle, Clock, Loader2, SkipForward, RotateCcw, Settings2, ChevronDown, ArchiveRestore, FilePlus2,
  Link2, Unlink, Pencil, VideoOff, Search,
  ArrowDownToLine, FileCode, FileText, AlignLeft, FileDown,
} from "lucide-react";
import { cn, formatDate, formatDateTimeShort } from "@/lib/utils";
import { apiClient } from "@/api/client";
import { StatusBadge, type ProcessingStatus } from "@/components/ui/status-badge";
import { ProgressBar } from "@/components/ui/progress-bar";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Modal } from "@/components/ui/modal";
import { ActionButton } from "@/components/ui/action-button";
import { RunConfigModal } from "@/components/recordings/run-config-modal";
import { POLL_INTERVAL_DETAIL, needsActivePoll } from "@/lib/constants";
import { VideoPlayer, type VideoPlayerMarker } from "@/components/ui/video-player";

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
  duration_seconds?: number | null;
}

interface OutputTarget {
  id: number;
  target_type: string;
  status: string;
  target_meta: Record<string, unknown>;
  failed: boolean;
  failed_reason: string | null;
  started_at: string | null;
  uploaded_at: string | null;
  duration_seconds: number | null;
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
  main_topics?: string[];
  summary?: string;
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
  on_air: boolean;
  source: SourceResponse | null;
  outputs: OutputTarget[];
  processing_stages: ProcessingStage[];
  download_started_at: string | null;
  downloaded_at: string | null;
  download_duration_seconds: number | null;
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

function formatStageTime(completedAt: string | null): string {
  if (!completedAt) return "";
  return new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(new Date(completedAt));
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
  const time = formatStageTime(stage.completed_at);

  return (
    <div className="py-1.5">
      <div className="flex items-center gap-2">
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
      {time && (
        <p className="ml-[21px] text-[10px] text-gray-300">{time}</p>
      )}
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
  const uploadDur = formatStageDuration(output.started_at, output.uploaded_at);

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
          <p className="text-[10px] text-gray-400">
            {formatDateTimeShort(output.uploaded_at)}
            {uploadDur && <span className="ml-1 tabular-nums">· {uploadDur}</span>}
          </p>
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
          <ActionButton
            size="sm"
            variant="secondary"
            onClick={() => onUpload(output.target_type)}
            isPending={uploadPending}
            icon={<Upload size={10} />}
            className="px-2 py-0.5 text-[11px] hover:border-[#224C87] hover:bg-[#224C87] hover:text-white"
          >
            {output.status === "FAILED" ? "Retry" : "Upload"}
          </ActionButton>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// RecordingVideoPlayer
// ---------------------------------------------------------------------------

const RecordingVideoPlayer = forwardRef<HTMLVideoElement, {
  recordingId: string;
  variant: "processed" | "original";
  vttBlobUrl?: string | null;
  markers?: VideoPlayerMarker[];
  onTimeUpdate?: (currentTime: number) => void;
}>(function RecordingVideoPlayer({ recordingId, variant, vttBlobUrl, markers, onTimeUpdate }, ref) {
  const { data: src, isLoading: loading, isError, refetch } = useQuery({
    queryKey: ["recording-media", recordingId, variant],
    queryFn: async () => {
      const res = await apiClient.get<{ url: string; expires_in: number }>(
        `/recordings/${recordingId}/media?type=${variant}`,
      );
      return res.data.url;
    },
  });

  if (loading) {
    return (
      <div className="flex aspect-video w-full items-center justify-center rounded-xl bg-[#F5F5F5]">
        <Loader2 size={20} className="animate-spin text-gray-300" />
      </div>
    );
  }

  if (isError || !src) {
    return (
      <div className="flex aspect-video w-full flex-col items-center justify-center gap-2 rounded-xl bg-[#F5F5F5]">
        <VideoOff size={22} className="text-gray-300" />
        <p className="text-xs text-gray-400">{isError ? "Не удалось загрузить видео" : "Видео пока недоступно"}</p>
        {isError && (
          <button type="button" onClick={() => void refetch()} className="text-xs text-[#224C87] hover:underline">
            Повторить
          </button>
        )}
      </div>
    );
  }

  return (
    <VideoPlayer
      ref={ref}
      src={src}
      vttBlobUrl={vttBlobUrl}
      markers={markers}
      onTimeUpdate={onTimeUpdate}
    />
  );
});

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
  const videoRef = useRef<HTMLVideoElement>(null);
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [resetConfirm, setResetConfirm] = useState(false);
  const [resetDeleteFiles, setResetDeleteFiles] = useState(false);
  const [runConfigOpen, setRunConfigOpen] = useState(false);
  const [configEditOpen, setConfigEditOpen] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [mediaDownloadError, setMediaDownloadError] = useState<string | null>(null);
  const [createTemplateOpen, setCreateTemplateOpen] = useState(false);
  const [createTemplateName, setCreateTemplateName] = useState("");
  const [bindTemplateOpen, setBindTemplateOpen] = useState(false);
  const [bindTemplateSearch, setBindTemplateSearch] = useState("");
  const [nameEditing, setNameEditing] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const [vttBlobUrl, setVttBlobUrl] = useState<string | null>(null);
  const [activeChapterIdx, setActiveChapterIdx] = useState(-1);
  const [chaptersOpen, setChaptersOpen] = useState(true);
  const chapterItemRefs = useRef<(HTMLButtonElement | null)[]>([]);

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
    staleTime: 10_000,
    refetchInterval: (q) => {
      const d = q.state.data;
      return d && needsActivePoll(d) ? POLL_INTERVAL_DETAIL : false;
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

  const renameRec = useMutation({
    mutationFn: (display_name: string) => apiClient.patch(`/recordings/${id}`, { display_name }),
    onSuccess: () => {
      setNameEditing(false);
      qc.invalidateQueries({ queryKey: ["recording", id] });
    },
  });

  function invalidateConfigQueries() {
    qc.invalidateQueries({ queryKey: ["recording", id] });
    qc.invalidateQueries({ queryKey: ["recording-config", Number(id)] });
  }

  const resetConfig = useMutation({
    mutationFn: () => apiClient.delete(`/recordings/${id}/config`),
    onSuccess: invalidateConfigQueries,
  });

  const bindTemplate = useMutation({
    mutationFn: (templateId: number) => apiClient.post(`/recordings/${id}/template/${templateId}`),
    onSuccess: () => {
      setBindTemplateOpen(false);
      invalidateConfigQueries();
    },
  });

  const unbindTemplate = useMutation({
    mutationFn: () => apiClient.delete(`/recordings/${id}/template`),
    onSuccess: invalidateConfigQueries,
  });

  const { data: bindTemplatesData } = useQuery<{ items: { id: number; name: string }[] }>({
    queryKey: ["templates-bind-list"],
    queryFn: async () => (await apiClient.get("/templates?per_page=100")).data,
    enabled: bindTemplateOpen,
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

  useEffect(() => {
    if (!recording?.subtitles?.vtt?.exists) return;
    let cancelled = false;
    let objectUrl: string | null = null;
    apiClient.get(`/recordings/${id}/files/vtt`, { responseType: "blob" })
      .then((res) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(res.data as Blob);
        setVttBlobUrl(objectUrl);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      setVttBlobUrl(null);
    };
  }, [id, recording?.subtitles?.vtt?.exists]);

  // useMemo keeps topicTimestamps reference stable — prevents VTT useEffect from looping
  const activeTopicVersion = useMemo<TopicVersion | null>(() => {
    if (!recording?.topics?.exists || !recording.topics.versions?.length) return null;
    const activeId = recording.topics.active_version;
    return activeId
      ? (recording.topics.versions.find((v) => v.id === activeId) ?? recording.topics.versions[0])
      : recording.topics.versions[0];
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recording?.topics?.versions]);

  const topicTimestamps = useMemo<TopicTimestamp[]>(
    () => activeTopicVersion?.topic_timestamps ?? [],
    [activeTopicVersion]
  );

  const mainTopics: string[] = activeTopicVersion?.main_topics ?? [];

  const handleTimeUpdate = useCallback((ct: number) => {
    const idx = topicTimestamps.findLastIndex((t) => t.start <= ct);
    setActiveChapterIdx(idx);
  }, [topicTimestamps]);

  useEffect(() => {
    if (activeChapterIdx < 0 || !chaptersOpen) return;
    chapterItemRefs.current[activeChapterIdx]?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [activeChapterIdx, chaptersOpen]);

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
        started_at: recording.download_started_at,
        completed_at: recording.downloaded_at,
        retry_count: 0,
        duration_seconds: recording.download_duration_seconds,
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
        {nameEditing ? (
          <form
            className="min-w-0 flex-1 flex items-center gap-2"
            onSubmit={(e) => { e.preventDefault(); if (nameDraft.trim()) renameRec.mutate(nameDraft.trim()); }}
          >
            <input
              autoFocus
              value={nameDraft}
              onChange={(e) => setNameDraft(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Escape") setNameEditing(false); }}
              className="flex-1 truncate rounded-lg border border-[#224C87] bg-white px-2 py-1 text-lg font-semibold text-gray-900 outline-none"
            />
            <button type="submit" disabled={renameRec.isPending || !nameDraft.trim()} className="text-xs text-[#224C87] hover:underline disabled:opacity-40">Сохранить</button>
            <button type="button" onClick={() => setNameEditing(false)} className="text-xs text-gray-400 hover:underline">Отмена</button>
          </form>
        ) : (
          <div className="min-w-0 flex-1 flex items-center gap-2 group">
            <h1 className="min-w-0 truncate text-lg font-semibold text-gray-900">
              {recording.display_name}
            </h1>
            <button
              type="button"
              onClick={() => { setNameDraft(recording.display_name); setNameEditing(true); }}
              className="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity text-gray-400 hover:text-gray-600"
              title="Переименовать"
            >
              <Pencil size={14} />
            </button>
          </div>
        )}
        <StatusBadge status={recording.status} failed={recording.failed} />
      </div>
      {recording.status === "DOWNLOADING" && recording.source?.source_type !== "LOCAL_FILE" && (
        <ProgressBar variant="indeterminate" className="mt-2 mb-1" />
      )}

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
          <div className="rounded-2xl border border-[#D9D9D9] bg-white p-5 shadow-sm">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500">Видео</h2>
            </div>
            {!hasVideoFiles ? (
              <div className="flex aspect-video w-full flex-col items-center justify-center gap-2 rounded-xl bg-[#F5F5F5]">
                <VideoOff size={22} className="text-gray-300" />
                <p className="text-xs text-gray-400">Видео пока недоступно</p>
              </div>
            ) : (
              <>
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
                    ref={videoRef}
                    key={`${id}-processed`}
                    recordingId={id}
                    variant="processed"
                    vttBlobUrl={vttBlobUrl}
                    markers={topicTimestamps.map((t) => ({ time: t.start, label: t.topic }))}
                    onTimeUpdate={handleTimeUpdate}
                  />
                )}
                {videoTab === "original" && hasOriginalVid && (
                  <RecordingVideoPlayer
                    ref={videoRef}
                    key={`${id}-original`}
                    recordingId={id}
                    variant="original"
                    vttBlobUrl={vttBlobUrl}
                    markers={topicTimestamps.map((t) => ({ time: t.start, label: t.topic }))}
                    onTimeUpdate={handleTimeUpdate}
                  />
                )}
                {topicTimestamps.length > 0 && (
                  <div className="mt-4 border-t border-[#F0F0F0] pt-3">
                    {mainTopics.length > 0 && (
                      <div className="mb-3">
                        <p className="text-base font-semibold leading-snug text-gray-900">
                          {mainTopics[0]}
                        </p>
                        {mainTopics.length > 1 && (
                          <p className="mt-0.5 text-sm text-gray-500">
                            {mainTopics.slice(1).join("  ·  ")}
                          </p>
                        )}
                      </div>
                    )}
                    <button
                      type="button"
                      onClick={() => setChaptersOpen((v) => !v)}
                      className="mb-1 flex w-full items-center gap-1.5 py-0.5 text-left"
                    >
                      <ChevronDown
                        size={13}
                        className={cn(
                          "shrink-0 text-gray-400 transition-transform duration-200",
                          !chaptersOpen && "-rotate-90"
                        )}
                      />
                      <span className="text-xs font-semibold uppercase tracking-wider text-gray-400">
                        Главы ({topicTimestamps.length})
                      </span>
                    </button>
                    {chaptersOpen && (
                      <div className="max-h-48 overflow-y-auto">
                        {topicTimestamps.map((t, i) => (
                          <button
                            key={i}
                            ref={(el) => { chapterItemRefs.current[i] = el; }}
                            type="button"
                            onClick={() => {
                              if (videoRef.current) {
                                videoRef.current.currentTime = t.start;
                                videoRef.current.play().catch(() => {});
                              }
                            }}
                            className={cn(
                              "flex w-full items-center gap-3 rounded-lg px-2 py-1.5 text-left transition-colors",
                              i === activeChapterIdx ? "bg-[#224C87]/6" : "hover:bg-gray-50"
                            )}
                          >
                            <span className={cn(
                              "h-1.5 w-1.5 shrink-0 rounded-full transition-colors",
                              i === activeChapterIdx ? "bg-[#224C87]" : "bg-[#D9D9D9]"
                            )} />
                            <span className={cn(
                              "w-11 shrink-0 font-mono text-xs",
                              i === activeChapterIdx ? "font-semibold text-[#224C87]" : "text-gray-400"
                            )}>
                              {formatTimecode(t.start)}
                            </span>
                            <span className={cn(
                              "flex-1 truncate text-sm",
                              i === activeChapterIdx ? "font-medium text-gray-900" : "text-gray-700"
                            )}>
                              {t.topic}
                            </span>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </>
            )}
          </div>

          {/* Media & Downloads */}
          {showMediaSection && (
            <div className="rounded-2xl border border-[#D9D9D9] bg-white p-5 shadow-sm">
              <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-500">
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
                    className="inline-flex items-center gap-1.5 rounded-lg border border-[#D9D9D9] bg-[#F5F5F5] px-2.5 py-1.5 text-xs text-gray-600 transition-colors hover:border-[#224C87]/30 hover:bg-[#224C87]/5 hover:text-[#224C87]"
                  >
                    <FileText size={12} className="shrink-0" />
                    SRT
                    <ArrowDownToLine size={11} className="shrink-0 text-gray-400" />
                  </button>
                )}
                {recording.subtitles?.vtt?.exists && (
                  <button
                    type="button"
                    onClick={() => downloadArtifact("vtt", `${dlStem}.vtt`)}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-[#D9D9D9] bg-[#F5F5F5] px-2.5 py-1.5 text-xs text-gray-600 transition-colors hover:border-[#224C87]/30 hover:bg-[#224C87]/5 hover:text-[#224C87]"
                  >
                    <FileText size={12} className="shrink-0" />
                    VTT
                    <ArrowDownToLine size={11} className="shrink-0 text-gray-400" />
                  </button>
                )}
                {recording.transcription?.exists && (
                  <>
                    <button
                      type="button"
                      onClick={() => downloadArtifact("transcript_json", `${dlStem}_transcript.json`)}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-[#D9D9D9] bg-[#F5F5F5] px-2.5 py-1.5 text-xs text-gray-600 transition-colors hover:border-[#224C87]/30 hover:bg-[#224C87]/5 hover:text-[#224C87]"
                    >
                      <FileCode size={12} className="shrink-0" />
                      Транскрипция JSON
                      <ArrowDownToLine size={11} className="shrink-0 text-gray-400" />
                    </button>
                    <button
                      type="button"
                      onClick={() => downloadArtifact("transcript_txt", `${dlStem}_transcript.txt`)}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-[#D9D9D9] bg-[#F5F5F5] px-2.5 py-1.5 text-xs text-gray-600 transition-colors hover:border-[#224C87]/30 hover:bg-[#224C87]/5 hover:text-[#224C87]"
                    >
                      <FileText size={12} className="shrink-0" />
                      Транскрипция TXT
                      <ArrowDownToLine size={11} className="shrink-0 text-gray-400" />
                    </button>
                    <button
                      type="button"
                      onClick={() => downloadArtifact("transcript_words", `${dlStem}_words.txt`)}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-[#D9D9D9] bg-[#F5F5F5] px-2.5 py-1.5 text-xs text-gray-600 transition-colors hover:border-[#224C87]/30 hover:bg-[#224C87]/5 hover:text-[#224C87]"
                    >
                      <AlignLeft size={12} className="shrink-0" />
                      Слова TXT
                      <ArrowDownToLine size={11} className="shrink-0 text-gray-400" />
                    </button>
                  </>
                )}
                {(recordingConfig?.metadata_config?.title_template || recordingConfig?.metadata_config?.description_template) && (
                  <button
                    type="button"
                    onClick={() => downloadArtifact("description_txt", `${dlStem}_description.txt`)}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-[#D9D9D9] bg-[#F5F5F5] px-2.5 py-1.5 text-xs text-gray-600 transition-colors hover:border-[#224C87]/30 hover:bg-[#224C87]/5 hover:text-[#224C87]"
                  >
                    <FileDown size={12} className="shrink-0" />
                    Описание TXT
                    <ArrowDownToLine size={11} className="shrink-0 text-gray-400" />
                  </button>
                )}
              </div>
            </div>
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
              <>
              <div className="mb-3 flex flex-wrap gap-2">
                <ActionButton
                  size="sm"
                  variant="secondary"
                  onClick={() => setConfigEditOpen(true)}
                  icon={<Pencil size={12} />}
                  className="hover:border-[#224C87] hover:bg-[#224C87]/5 hover:text-[#224C87]"
                >
                  Редактировать
                </ActionButton>
                {recordingConfig.has_manual_override && (
                  <ActionButton
                    size="sm"
                    variant="secondary"
                    isPending={resetConfig.isPending}
                    onClick={() => resetConfig.mutate()}
                    icon={<RotateCcw size={12} />}
                    pendingLabel="Сброс…"
                  >
                    Сбросить override
                  </ActionButton>
                )}
              </div>
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
              </>
            )}
          </CollapsibleCard>

        </div>

        {/* ════ SIDEBAR ════ */}
        <div className="w-full space-y-5 lg:w-80 lg:shrink-0">

          {/* Control Panel */}
          <div className="rounded-2xl border border-[#D9D9D9] bg-white p-4 shadow-sm">
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-500">Управление</h2>
            {isSoftDeleted ? (
              <ActionButton
                disabled={isActing}
                isPending={restoreRec.isPending}
                onClick={() => restoreRec.mutate()}
                icon={<ArchiveRestore size={15} />}
                pendingLabel="Восстановление…"
                className="w-full justify-center py-2.5 font-semibold bg-green-600 hover:bg-green-700 disabled:cursor-not-allowed"
              >
                Восстановить
              </ActionButton>
            ) : (
              <div className="space-y-3">
                <div>
                  <div className={cn(
                    "flex overflow-hidden rounded-xl border",
                    !recording.can_run || isActing
                      ? "border-[#D9D9D9] opacity-60"
                      : "border-[#224C87]"
                  )}>
                    <button
                      type="button"
                      disabled={!recording.can_run || isActing}
                      onClick={() => run.mutate()}
                      className={cn(
                        "flex flex-1 items-center justify-center gap-2 px-4 py-2.5 text-sm font-semibold transition-colors disabled:cursor-not-allowed",
                        !recording.can_run || isActing
                          ? "bg-gray-100 text-gray-400"
                          : "bg-[#224C87] text-white hover:bg-[#1a3a6b]"
                      )}
                    >
                      {run.isPending ? (
                        <Loader2 size={14} className="animate-spin" />
                      ) : (
                        <Play size={14} />
                      )}
                      {run.isPending ? "Запуск…" : "Запустить"}
                    </button>
                    <button
                      type="button"
                      disabled={!recording.can_run || isActing}
                      onClick={() => setRunConfigOpen(true)}
                      title="С конфигурацией"
                      className={cn(
                        "flex w-10 shrink-0 items-center justify-center border-l transition-colors disabled:cursor-not-allowed",
                        !recording.can_run || isActing
                          ? "border-[#D9D9D9] bg-gray-100 text-gray-400"
                          : "border-[#1a3a6b] bg-[#224C87] text-white hover:bg-[#1a3a6b]"
                      )}
                    >
                      <Settings2 size={14} />
                    </button>
                  </div>
                </div>
                <div className="space-y-2 border-t border-[#F5F5F5] pt-2">
                  <div className="flex gap-2">
                    <ActionButton
                      variant="secondary"
                      disabled={!recording.can_pause || isActing}
                      isPending={pause.isPending}
                      onClick={() => pause.mutate()}
                      icon={<Pause size={13} />}
                      pendingLabel="…"
                      className="flex-1 justify-center py-2 disabled:cursor-not-allowed"
                    >
                      Пауза
                    </ActionButton>
                    <ActionButton
                      variant="secondary"
                      disabled={isActing}
                      isPending={resetRec.isPending}
                      onClick={() => setResetConfirm(true)}
                      icon={<RotateCcw size={13} />}
                      pendingLabel="…"
                      className="flex-1 justify-center py-2 disabled:cursor-not-allowed"
                    >
                      Сброс
                    </ActionButton>
                  </div>
                  <div className="flex gap-2">
                    <ActionButton
                      variant="secondary"
                      onClick={() => { setCreateTemplateName(recording.display_name); setCreateTemplateOpen(true); }}
                      icon={<FilePlus2 size={13} />}
                      className="flex-1 justify-center hover:border-[#224C87]/40 hover:bg-[#224C87]/5 hover:text-[#224C87]"
                    >
                      Создать шаблон
                    </ActionButton>
                    {(recordingConfig?.is_mapped ?? recording.is_mapped) ? (
                      <ActionButton
                        variant="secondary"
                        isPending={unbindTemplate.isPending}
                        onClick={() => unbindTemplate.mutate()}
                        title="Отвязать шаблон"
                        icon={<Unlink size={13} />}
                        className="justify-center py-2"
                      />
                    ) : (
                      <ActionButton
                        variant="secondary"
                        onClick={() => setBindTemplateOpen(true)}
                        title="Привязать шаблон"
                        icon={<Link2 size={13} />}
                        className="justify-center py-2 hover:border-[#224C87]/40 hover:bg-[#224C87]/5 hover:text-[#224C87]"
                      />
                    )}
                  </div>
                </div>
                <div className="border-t border-[#F5F5F5] pt-2">
                  <ActionButton
                    variant="secondary"
                    disabled={isActing}
                    onClick={() => setDeleteConfirm(true)}
                    icon={<Trash2 size={13} />}
                    className="w-full justify-center border-red-200 py-2 text-red-500 hover:bg-red-50 disabled:cursor-not-allowed"
                  >
                    Удалить
                  </ActionButton>
                </div>
              </div>
            )}
          </div>

          {/* Pipeline */}
          <div className="rounded-2xl border border-[#D9D9D9] bg-white p-4 shadow-sm">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500">Пайплайн</h2>
              <div className="flex items-center gap-2">
                {allPipelineStages.length > 0 && (() => {
                  const completed = allPipelineStages.filter((s) => s.status === "COMPLETED" || s.status === "SKIPPED").length;
                  const hasFailed = allPipelineStages.some((s) => s.failed);
                  const total = allPipelineStages.length;
                  return (
                    <span className={cn(
                      "rounded-full px-2 py-0.5 text-[10px] font-medium",
                      hasFailed ? "bg-red-50 text-red-600" : completed === total ? "bg-green-50 text-green-700" : "bg-gray-100 text-gray-500"
                    )}>
                      {completed}/{total}
                    </span>
                  );
                })()}
                {recording.pipeline_duration_seconds != null && recording.pipeline_duration_seconds > 0 && (
                  <span className="text-[10px] text-gray-400">
                    ~{Math.round(recording.pipeline_duration_seconds)} с
                  </span>
                )}
              </div>
            </div>
            {allPipelineStages.length === 0 ? (
              <p className="text-xs text-gray-400">Нет данных</p>
            ) : (
              <div className="divide-y divide-[#F5F5F5]">
                {allPipelineStages.map((s) => {
                  const canon = normalizeStageType(s.stage_type);
                  return (
                    <PipelineCompactRow key={canon} stage={s} />
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
              {recording.source?.source_type && (
                <SidebarInfoRow label="Источник" value={recording.source.source_type} />
              )}
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

      <RunConfigModal
        open={configEditOpen}
        onClose={() => setConfigEditOpen(false)}
        mode="single"
        submitMode="save"
        recordingId={Number(id)}
        recordingName={recording.display_name}
      />

      {/* Bind to existing template modal */}
      <Modal
        open={bindTemplateOpen}
        onClose={() => { setBindTemplateOpen(false); setBindTemplateSearch(""); }}
        label="Привязать шаблон"
        panelClassName="max-w-sm"
      >
        <div className="p-6">
          <h2 className="mb-4 text-sm font-semibold text-gray-900">Привязать к шаблону</h2>
          {bindTemplate.isError && (
            <p className="mb-3 text-xs text-red-500">
              {(bindTemplate.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Ошибка"}
            </p>
          )}
          <div className="relative mb-3">
            <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              placeholder="Поиск шаблонов…"
              value={bindTemplateSearch}
              onChange={(e) => setBindTemplateSearch(e.target.value)}
              className="w-full rounded-xl border border-[#D9D9D9] py-2 pl-8 pr-3 text-sm outline-none focus:border-[#224C87] focus:ring-1 focus:ring-[#224C87]/20"
            />
          </div>
          <div className="max-h-64 space-y-1.5 overflow-y-auto">
            {(() => {
              const allItems = bindTemplatesData?.items ?? [];
              const filtered = bindTemplateSearch.trim()
                ? allItems.filter((t) => t.name.toLowerCase().includes(bindTemplateSearch.toLowerCase()))
                : allItems;
              if (filtered.length === 0) {
                return <p className="py-6 text-center text-sm text-gray-400">{allItems.length === 0 ? "Нет шаблонов" : "Ничего не найдено"}</p>;
              }
              return filtered.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  disabled={bindTemplate.isPending}
                  onClick={() => { bindTemplate.mutate(t.id); setBindTemplateSearch(""); }}
                  className="flex w-full items-center justify-between gap-2 rounded-xl border border-[#D9D9D9] bg-white px-3 py-2.5 text-left text-sm font-medium text-gray-800 transition-colors hover:border-[#224C87] hover:bg-[#224C87]/5 disabled:opacity-50"
                >
                  <span className="min-w-0 truncate">{t.name}</span>
                  <Link2 size={13} className="shrink-0 text-gray-400" />
                </button>
              ));
            })()}
          </div>
          <div className="flex justify-end pt-4">
            <ActionButton variant="secondary" onClick={() => { setBindTemplateOpen(false); setBindTemplateSearch(""); }}>
              Отмена
            </ActionButton>
          </div>
        </div>
      </Modal>

      {/* Create template modal */}
      <Modal
        open={createTemplateOpen}
        onClose={() => setCreateTemplateOpen(false)}
        label="Создать шаблон из записи"
        panelClassName="max-w-sm"
      >
        <div className="p-6">
          <h2 className="mb-4 text-sm font-semibold text-gray-900">Создать шаблон из записи</h2>
          <div className="space-y-3">
            <div className="space-y-1">
              <label htmlFor="new-template-name" className="text-xs font-medium text-gray-500">
                Название шаблона
              </label>
              <input
                id="new-template-name"
                type="text"
                autoFocus
                value={createTemplateName}
                onChange={(e) => setCreateTemplateName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && createTemplateName.trim()) {
                    createTemplate.mutate(createTemplateName.trim());
                  }
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
              <ActionButton variant="secondary" onClick={() => setCreateTemplateOpen(false)}>
                Отмена
              </ActionButton>
              <ActionButton
                disabled={!createTemplateName.trim()}
                isPending={createTemplate.isPending}
                isSuccess={createTemplate.isSuccess}
                onClick={() => createTemplate.mutate(createTemplateName.trim())}
                icon={<FilePlus2 size={14} />}
                pendingLabel="Создание…"
                className="font-semibold"
              >
                Создать
              </ActionButton>
            </div>
          </div>
        </div>
      </Modal>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helper row components
// ---------------------------------------------------------------------------

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
