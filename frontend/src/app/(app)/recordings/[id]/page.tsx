"use client";

import { use, useState, useRef, useEffect, useCallback, useMemo, forwardRef, type ComponentType, type ReactNode } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft, Play, Pause, Trash2, Upload, ExternalLink,
  CheckCircle2, XCircle, Clock, Loader2, RotateCcw, Settings2, ArchiveRestore, FilePlus2,
  Link2, Unlink, Pencil, VideoOff, Search, Share2, Check, X, Code2,
} from "lucide-react";
import { cn, formatDate, formatDateTimeShort, formatDuration, extractApiError } from "@/lib/utils";
import { apiClient } from "@/api/client";
import { StatusBadge, type ProcessingStatus } from "@/components/ui/status-badge";
import { ProgressBar } from "@/components/ui/progress-bar";
import { CANONICAL_STAGE_ORDER, PipelineStageList, formatFailedStage, normalizeStageType } from "@/components/recordings/pipeline-stages";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Modal } from "@/components/ui/modal";
import { ActionButton } from "@/components/ui/action-button";
import { ErrorState } from "@/components/ui/error-state";
import { CollapsibleCard, SectionCard } from "@/components/ui/section-card";
import { Tabs, type TabItem } from "@/components/ui/tabs";
import { ArtefactList, type ArtefactItem } from "@/components/recordings/artefact-list";
import { RunConfigModal } from "@/components/recordings/run-config-modal";
import { AIContentEditor } from "@/components/recordings/ai-content-editor";
import { ShareModal } from "@/components/recordings/share-modal";
import { TemplateField } from "@/components/platforms/platform-fields";
import { POLL_INTERVAL_DETAIL, needsActivePoll } from "@/lib/constants";
import { VideoPlayer, type VideoPlayerMarker } from "@/components/ui/video-player";
import { VIDEO_PLAYER_FRAME, VideoPlayerLoading } from "@/components/ui/video-player-frame";
import { Toast } from "@/components/ui/toast";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";

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
  description?: string;
  questions?: string[];
  topic_timestamps?: TopicTimestamp[];
  manually_edited?: boolean;
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
  share_token?: string | null;
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
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

/** Sidebar/detail template line with optional link to /templates/:id (preset row styling). */
function renderRecordingTemplateNavValue(opts: {
  isMapped: boolean;
  templateId: number | null;
  templateName: string | null;
}): ReactNode {
  const { isMapped, templateId, templateName } = opts;
  if (!isMapped) return "Not linked";
  const tid = templateId ?? null;
  const nameTrimmed = templateName?.trim();
  const name = nameTrimmed ? nameTrimmed : null;
  if (tid != null) {
    const linkText = name ?? `#${tid}`;
    return (
      <Link
        href={`/templates/${tid}`}
        title={linkText}
        className="inline-block truncate text-xs text-foreground transition-colors hover:text-primary"
      >
        {linkText}
      </Link>
    );
  }
  if (name) return name;
  return "Linked";
}

// ---------------------------------------------------------------------------
// Pipeline stage helpers
// ---------------------------------------------------------------------------

/**
 * Page padding matches every other app page. The width cap is local to this
 * page: it is the only one carrying long prose (description, summary), and
 * without it those run the full width of a wide monitor, far past a readable
 * measure.
 */
const PAGE_ROOT = "w-full min-w-0 max-w-[110rem] p-6 sm:p-8";

/** Shared by the loaded page and its skeleton so column order cannot drift. */
const DETAIL_COLUMNS = "flex flex-col gap-6 lg:flex-row lg:items-start";
const DETAIL_MAIN = "min-w-0 flex-1 space-y-6";
const DETAIL_SIDEBAR = "order-first w-full space-y-6 lg:order-none lg:w-80 lg:shrink-0";

/** Section labels — one source for cards and the loading shell. */
const RECORDING_SECTION = {
  video: "Video",
  description: "Description",
  chapters: "Chapters & summary",
  configuration: "Configuration",
  controlPanel: "Control panel",
  details: "Details",
  publications: "Publications",
  files: "Files",
  pipeline: "Pipeline",
} as const;

const CONTROL_PANEL_ACTION_GRID = "grid grid-cols-1 gap-1.5 min-[380px]:grid-cols-2";

const VIDEO_VARIANT_TABS: TabItem<"processed" | "original">[] = [
  { value: "processed", label: "Processed" },
  { value: "original", label: "Original" },
];

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
  if (st === "EXPIRED") return { phase: "skipped", hint: "Recording is unavailable or expired" };
  if (["DOWNLOADED", "PROCESSING", "PROCESSED", "UPLOADING", "UPLOADED", "READY", "SKIPPED"].includes(st)) {
    return { phase: "done" };
  }
  return { phase: "pending" };
}

const TARGET_LABELS: Record<string, string> = {
  YOUTUBE:     "YouTube",
  VK:          "VK",
  YANDEX_DISK: "Yandex Disk",
};

const PLATFORM_STATUS_CONFIG: Record<string, { icon: ComponentType<{ size?: number; className?: string }>; label: string; color: string }> = {
  UPLOADED:     { icon: CheckCircle2, label: "Published",    color: "text-success-fg" },
  UPLOADING:    { icon: Loader2,      label: "Publishing…",  color: "text-primary" },
  FAILED:       { icon: XCircle,      label: "Failed",       color: "text-danger-fg" },
  NOT_UPLOADED: { icon: Clock,        label: "Not uploaded", color: "text-muted-foreground" },
};


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
          <span className="text-xs font-semibold text-foreground">{label}</span>
          {output.preset && (
            <Link
              href={`/presets/${output.preset.id}`}
              className="text-xs text-muted-foreground transition-colors hover:text-primary"
            >
              {output.preset.name}
            </Link>
          )}
        </div>
        <p className={cn("text-xs", cfg.color)}>{cfg.label}</p>
        {output.failed_reason && (
          <p className="break-words text-xs text-danger-fg">{output.failed_reason}</p>
        )}
        {output.uploaded_at && (
          <p className="text-xs text-muted-foreground">
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
            className="flex items-center gap-0.5 text-xs font-medium text-primary hover:underline"
          >
            Open <ExternalLink size={10} />
          </a>
        )}
        {(canUpload || output.status === "FAILED") && (
          <ActionButton
            size="sm"
            variant="secondary"
            onClick={() => onUpload(output.target_type)}
            isPending={uploadPending}
            icon={<Upload size={10} />}
            className="px-2 py-0.5 text-xs hover:border-primary hover:bg-primary hover:text-white"
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
    return <VideoPlayerLoading />;
  }

  if (isError || !src) {
    return (
      <div className={cn(VIDEO_PLAYER_FRAME, "flex flex-col items-center justify-center gap-2 bg-muted")}>
        <VideoOff size={22} className="text-muted-foreground" />
        <p className="text-xs text-muted-foreground">{isError ? "Failed to load video" : "Video not available yet"}</p>
        {isError && (
          <button type="button" onClick={() => void refetch()} className="text-xs text-primary hover:underline">
            Retry
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
// Main page
// ---------------------------------------------------------------------------

export default function RecordingDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const qc = useQueryClient();
  const { toast, show: showToast, dismiss: dismissToast } = useToast();
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
  const [shareOpen, setShareOpen] = useState(false);
  // Optimistic override: undefined = use server value, string/null = local override after user action
  const [shareTokenOverride, setShareTokenOverride] = useState<string | null | undefined>(undefined);
  const [nameEditing, setNameEditing] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const [vttBlobUrl, setVttBlobUrl] = useState<string | null>(null);
  const [activeChapterIdx, setActiveChapterIdx] = useState(-1);
  const [descCollapsed, setDescCollapsed] = useState(true);
  const [descEditing, setDescEditing] = useState(false);
  const [descDraft, setDescDraft] = useState("");
  const [descIsTemplate, setDescIsTemplate] = useState(false);
  const [descSaving, setDescSaving] = useState(false);

  const { data: recordingConfig, isLoading: configLoading } = useQuery<RecordingConfigResponse>({
    queryKey: ["recording-config", Number(id)],
    queryFn: async () => (await apiClient.get<RecordingConfigResponse>(`/recordings/${id}/config`)).data,
  });

  const { data: recording, isLoading, error, refetch } = useQuery<RecordingDetail>({
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

  const shareToken = shareTokenOverride !== undefined ? shareTokenOverride : (recording?.share_token ?? null);

  const run = useMutation({
    mutationFn: () => apiClient.post(`/recordings/${id}/run`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["recording", id] });
      showToast("success", "Pipeline started");
    },
    onError: (e) => showToast("error", extractApiError(e, "Failed to start pipeline")),
  });

  const pause = useMutation({
    mutationFn: () => apiClient.post(`/recordings/${id}/pause`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["recording", id] });
      showToast("success", "Pipeline paused");
    },
    onError: (e) => showToast("error", extractApiError(e, "Failed to pause")),
  });

  const deleteRec = useMutation({
    mutationFn: () => apiClient.delete(`/recordings/${id}`),
    onSuccess: () => router.push("/recordings"),
    onError: (e) => showToast("error", extractApiError(e, "Failed to delete")),
  });

  const resetRec = useMutation({
    mutationFn: () => apiClient.post(`/recordings/${id}/reset`, null, { params: { delete_files: resetDeleteFiles } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["recording", id] });
      showToast("success", "Recording reset");
    },
    onError: (e) => showToast("error", extractApiError(e, "Failed to reset")),
  });

  const restoreRec = useMutation({
    mutationFn: () => apiClient.post(`/recordings/${id}/restore`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["recording", id] });
      showToast("success", "Recording restored");
    },
    onError: (e) => showToast("error", extractApiError(e, "Failed to restore")),
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
      showToast("success", "Name updated");
    },
    onError: (e) => showToast("error", extractApiError(e, "Failed to rename")),
  });

  function invalidateConfigQueries() {
    qc.invalidateQueries({ queryKey: ["recording", id] });
    qc.invalidateQueries({ queryKey: ["recording-config", Number(id)] });
  }

  const resetConfig = useMutation({
    mutationFn: () => apiClient.delete(`/recordings/${id}/config`),
    onSuccess: () => {
      invalidateConfigQueries();
      showToast("success", "Override removed");
    },
    onError: (e) => showToast("error", extractApiError(e, "Failed to reset config")),
  });

  const bindTemplate = useMutation({
    mutationFn: (templateId: number) => apiClient.post(`/recordings/${id}/template/${templateId}`),
    onSuccess: () => {
      setBindTemplateOpen(false);
      invalidateConfigQueries();
      showToast("success", "Template bound");
    },
  });

  const unbindTemplate = useMutation({
    mutationFn: () => apiClient.delete(`/recordings/${id}/template`),
    onSuccess: () => {
      invalidateConfigQueries();
      showToast("success", "Template unbound");
    },
    onError: (e) => showToast("error", extractApiError(e, "Failed to unbind")),
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
      showToast("success", "Upload started");
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

  const savedDescription = activeTopicVersion?.description;
  const directDescription =
    savedDescription && !savedDescription.includes("{{") ? savedDescription : null;

  const metadataConfig = recordingConfig?.metadata_config;
  const hasMetadataTemplates = Boolean(
    metadataConfig?.description_template || metadataConfig?.title_template
  );

  const descriptionTemplateSource = useMemo(() => {
    if (!hasMetadataTemplates) return null;
    if (savedDescription) return savedDescription.includes("{{") ? savedDescription : null;
    return metadataConfig?.description_template ?? null;
  }, [hasMetadataTemplates, savedDescription, metadataConfig?.description_template]);

  const titleTemplateSource = useMemo(() => {
    if (!hasMetadataTemplates) return null;
    if (savedDescription) return null;
    return metadataConfig?.title_template ?? null;
  }, [hasMetadataTemplates, savedDescription, metadataConfig?.title_template]);

  const { data: queriedDescription, isLoading: descriptionQueryLoading } = useQuery({
    queryKey: ["recording", id, "rendered-description", descriptionTemplateSource],
    queryFn: async () => {
      const res = await apiClient.post(`/recordings/${id}/topics/render`, {
        template: descriptionTemplateSource!,
      });
      return (res.data as { rendered: string }).rendered;
    },
    enabled: Boolean(descriptionTemplateSource),
    staleTime: 60_000,
  });

  const { data: queriedTitle, isLoading: titleQueryLoading } = useQuery({
    queryKey: ["recording", id, "rendered-title", titleTemplateSource],
    queryFn: async () => {
      const res = await apiClient.post(`/recordings/${id}/topics/render`, {
        template: titleTemplateSource!,
      });
      return (res.data as { rendered: string }).rendered;
    },
    enabled: Boolean(titleTemplateSource),
    staleTime: 60_000,
  });

  const displayDescription = directDescription ?? queriedDescription ?? null;
  const descriptionLoading = descriptionQueryLoading || titleQueryLoading;

  const handleTimeUpdate = useCallback((ct: number) => {
    const idx = topicTimestamps.findLastIndex((t) => t.start <= ct);
    setActiveChapterIdx(idx);
  }, [topicTimestamps]);

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

  // AI content (topics, summary, questions) is tied to the processed video timeline.
  const showTopics = !!activeTopicVersion && videoTab === "processed";

  const isActing = run.isPending || pause.isPending || deleteRec.isPending || resetRec.isPending || restoreRec.isPending;
  const isSoftDeleted = !!recording?.soft_deleted_at;

  if (isLoading) {
    return <RecordingDetailSkeleton />;
  }

  if (error || !recording) {
    // 404/403 means it's gone or belongs to someone else. Anything else is a
    // transport failure the reader can retry — don't claim it doesn't exist.
    const status = (error as { response?: { status?: number } } | null)?.response?.status;
    const missing = status === 404 || status === 403;
    return (
      <div className={PAGE_ROOT}>
        <ErrorState
          title={missing ? "Recording not found" : "Unable to load this recording"}
          description={
            missing
              ? "It may have been deleted, or it belongs to another account."
              : "Check your connection and try again."
          }
          onRetry={missing ? undefined : () => void refetch()}
        />
        <p className="text-center">
          <Link href="/recordings" className="text-sm text-primary hover:underline">
            Back to recordings
          </Link>
        </p>
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
      setMediaDownloadError(typeof detail === "string" ? detail : "Failed to download file");
    }
  }

  const dlStem = `recording-${recording.id}`;

  const artefacts: ArtefactItem[] = [
    ...(recording.transcription?.exists
      ? [
          { type: "transcript_json" as const, onDownload: () => downloadArtifact("transcript_json", `${dlStem}_transcript.json`) },
          { type: "transcript_txt" as const, onDownload: () => downloadArtifact("transcript_txt", `${dlStem}_transcript.txt`) },
          { type: "transcript_words" as const, onDownload: () => downloadArtifact("transcript_words", `${dlStem}_words.txt`) },
        ]
      : []),
    ...(recordingConfig?.metadata_config?.title_template || recordingConfig?.metadata_config?.description_template
      ? [{ type: "description_txt" as const, onDownload: () => downloadArtifact("description_txt", `${dlStem}_description.txt`) }]
      : []),
    ...(recording.subtitles?.srt?.exists
      ? [{ type: "srt" as const, onDownload: () => downloadArtifact("srt", `${dlStem}.srt`) }]
      : []),
    ...(recording.subtitles?.vtt?.exists
      ? [{ type: "vtt" as const, onDownload: () => downloadArtifact("vtt", `${dlStem}.vtt`) }]
      : []),
  ];

  // One player node, reused whether or not the variant tabs are shown, so the
  // two branches can never drift apart. `videoTab` is already resolved to a
  // variant that exists, and this only renders when a video file is present.
  const videoPlayerNode = (
    <div key={`${id}-${videoTab}-wrap`} className="animate-overlay-in">
      <RecordingVideoPlayer
        ref={videoRef}
        key={`${id}-${videoTab}`}
        recordingId={id}
        variant={videoTab}
        vttBlobUrl={vttBlobUrl}
        markers={
          videoTab === "processed"
            ? topicTimestamps.map((t) => ({ time: t.start, label: t.topic }))
            : []
        }
        onTimeUpdate={handleTimeUpdate}
      />
    </div>
  );

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
    <div className={PAGE_ROOT}>
      {/* ── Header ── */}
      <Link
        href="/recordings"
        className="mb-2 inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-secondary-foreground"
      >
        <ArrowLeft size={16} />
        Recordings
      </Link>
      <div className="mb-5 flex min-h-[2.5rem] flex-wrap items-center gap-x-3 gap-y-2">
        {nameEditing ? (
          <form
            className="flex min-w-0 flex-1 items-center gap-2"
            onSubmit={(e) => { e.preventDefault(); if (nameDraft.trim()) renameRec.mutate(nameDraft.trim()); }}
          >
            <input
              autoFocus
              aria-label="Recording name"
              value={nameDraft}
              onChange={(e) => setNameDraft(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Escape") setNameEditing(false); }}
              className="min-w-0 flex-1 rounded-lg border border-input bg-card px-2 py-1 text-2xl font-semibold tracking-tight text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/30"
            />
            <button type="submit" disabled={renameRec.isPending || !nameDraft.trim()} className="text-xs text-primary hover:underline disabled:opacity-40">Save</button>
            <button type="button" onClick={() => setNameEditing(false)} className="text-xs text-muted-foreground hover:underline">Cancel</button>
          </form>
        ) : (
          <div className="group flex min-w-0 flex-1 items-center gap-2">
            <h1 className="min-w-0 truncate text-2xl font-semibold tracking-tight text-foreground">
              {recording.display_name}
            </h1>
            {/* Revealed on hover for pointers, but always present where there
                is no hover — otherwise renaming does not exist on touch. */}
            <button
              type="button"
              onClick={() => { setNameDraft(recording.display_name); setNameEditing(true); }}
              className="shrink-0 rounded p-1 text-muted-foreground transition-opacity hover:text-secondary-foreground focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100"
              title="Rename"
              aria-label="Rename recording"
            >
              <Pencil size={14} />
            </button>
          </div>
        )}
        <StatusBadge status={recording.status} failed={recording.failed} failedStage={formatFailedStage(recording.failed_at_stage)} />
      </div>
      {recording.on_air && (
        <ProgressBar variant="indeterminate" className="mt-2 mb-1" />
      )}

      {/* ── Error banners ── */}
      {recording.failed && recording.failed_reason && (
        <div role="alert" className="mb-5 rounded-xl border border-danger-fg/40 bg-danger-fg/10 px-4 py-3 text-sm text-danger-fg">
          <span className="font-medium">Error:</span> {recording.failed_reason}
        </div>
      )}
      {uploadError && (
        <div role="alert" className="mb-5 rounded-xl border border-danger-fg/40 bg-danger-fg/10 px-4 py-3 text-sm text-danger-fg">
          {uploadError}
        </div>
      )}

      {/* ── 2-column layout ──
          The sidebar is the control surface, so below `lg` it comes first.
          Otherwise Run, Pause and Share sit under the video, description,
          AI-Data and Configuration cards. */}
      <div className={DETAIL_COLUMNS}>

        {/* ════ MAIN COLUMN ════ */}
        <div className={DETAIL_MAIN}>

          {/* Video */}
          <SectionCard title={RECORDING_SECTION.video} density="compact">
            {!hasVideoFiles ? (
              <div className="flex aspect-video w-full flex-col items-center justify-center gap-2 rounded-xl bg-muted">
                <VideoOff size={22} className="text-muted-foreground" />
                <p className="text-xs text-muted-foreground">Video not available yet</p>
              </div>
            ) : hasProcessedVid && hasOriginalVid ? (
              <Tabs
                items={VIDEO_VARIANT_TABS}
                value={videoTab}
                onChange={setVideoTabChoice}
                label="Video source"
              >
                {videoPlayerNode}
              </Tabs>
            ) : (
              videoPlayerNode
            )}
          </SectionCard>

          {/* Description. The subtitle carries only the rendered upload title:
              falling back to display_name would just repeat the <h1> above. */}
          {(displayDescription || queriedTitle || descriptionLoading) && (
            <CollapsibleCard
              title={RECORDING_SECTION.description}
              subtitle={queriedTitle && queriedTitle !== recording.display_name ? queriedTitle : undefined}
              open={!descCollapsed}
              onOpenChange={(open) => setDescCollapsed(!open)}
              action={
                !descCollapsed && !descEditing && !descriptionLoading ? (
                  <button
                    type="button"
                    onClick={() => {
                      const raw = activeTopicVersion?.description
                        ?? recordingConfig?.metadata_config?.description_template
                        ?? displayDescription
                        ?? "";
                      setDescDraft(raw);
                      setDescIsTemplate(raw.includes("{{"));
                      setDescEditing(true);
                    }}
                    className="flex shrink-0 items-center gap-1 rounded px-1 py-0.5 text-xs text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
                  >
                    <Pencil size={11} /> Edit
                  </button>
                ) : undefined
              }
            >
              {descriptionLoading ? (
                <div className="space-y-2">
                  <div className="h-3 w-3/5 animate-pulse rounded bg-muted" />
                  <div className="h-3 w-full animate-pulse rounded bg-muted mt-3" />
                  <div className="h-3 w-4/5 animate-pulse rounded bg-muted" />
                  <div className="h-3 w-3/5 animate-pulse rounded bg-muted" />
                </div>
              ) : descEditing ? (
                <div>
                  {descIsTemplate ? (
                    <TemplateField
                      label=""
                      value={descDraft}
                      onChange={(v) => { setDescDraft(v); setDescIsTemplate(v.includes("{{")); }}
                      multiline
                      rows={8}
                      placeholder="Description template…"
                    />
                  ) : (
                    <textarea
                      autoFocus
                      value={descDraft}
                      onChange={(e) => { setDescDraft(e.target.value); setDescIsTemplate(e.target.value.includes("{{")); }}
                      rows={8}
                      className="w-full resize-none rounded-lg border border-border bg-muted/30 px-3 py-2 text-sm outline-none focus:border-primary"
                      placeholder="Description…"
                    />
                  )}
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      disabled={descSaving}
                      onClick={async () => {
                        setDescSaving(true);
                        try {
                          await apiClient.patch(`/recordings/${id}/topics`, { description: descDraft });
                          await qc.invalidateQueries({ queryKey: ["recording", id] });
                          if (descDraft.includes("{{")) {
                            await qc.invalidateQueries({ queryKey: ["recording", id, "rendered-description"] });
                          }
                          setDescEditing(false);
                        } finally {
                          setDescSaving(false);
                        }
                      }}
                      className="flex items-center gap-1 rounded-md bg-primary px-2.5 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                    >
                      {descSaving ? <Loader2 size={11} className="animate-spin" /> : <Check size={11} />}
                      Save
                    </button>
                    {descIsTemplate && (
                      <button
                        type="button"
                        disabled={descSaving}
                        onClick={async () => {
                          setDescSaving(true);
                          try {
                            const res = await apiClient.post(`/recordings/${id}/topics/render`, { template: descDraft });
                            const rendered = (res.data as { rendered: string }).rendered;
                            setDescDraft(rendered);
                            setDescIsTemplate(false);
                            await apiClient.patch(`/recordings/${id}/topics`, { description: rendered });
                            await qc.invalidateQueries({ queryKey: ["recording", id] });
                            setDescEditing(false);
                          } finally {
                            setDescSaving(false);
                          }
                        }}
                        className="flex items-center gap-1 rounded-md border border-border px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground disabled:opacity-50"
                      >
                        {descSaving ? <Loader2 size={11} className="animate-spin" /> : <Code2 size={11} />}
                        Convert to text
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => setDescEditing(false)}
                      className="flex items-center gap-1 rounded-md border border-border px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground"
                    >
                      <X size={11} /> Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <p className="max-w-prose whitespace-pre-wrap text-sm leading-relaxed text-foreground">
                  {displayDescription}
                </p>
              )}
            </CollapsibleCard>
          )}

          {/* Chapters & summary — open by default: the chapter list is the page's
              most useful control, and the player's chapter-following writes
              into refs that only exist while this card is expanded. */}
          {showTopics && activeTopicVersion && (
            <CollapsibleCard title={RECORDING_SECTION.chapters} defaultOpen>
              <AIContentEditor
                recordingId={Number(id)}
                version={activeTopicVersion}
                onUpdated={() => {
                  qc.invalidateQueries({ queryKey: ["recording", id] });
                }}
                onSeek={(t) => {
                  if (videoRef.current) {
                    videoRef.current.currentTime = t;
                    videoRef.current.play().catch(() => {});
                  }
                }}
                activeChapterIdx={activeChapterIdx}
              />
            </CollapsibleCard>
          )}

          {/* Config (collapsible) */}
          <CollapsibleCard title={RECORDING_SECTION.configuration} defaultOpen={false}>
            {configLoading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 size={14} className="animate-spin" />
                Loading…
              </div>
            ) : !recordingConfig ? (
              <p className="text-sm text-muted-foreground">No data</p>
            ) : (
              <>
              <div className="mb-3 flex flex-wrap gap-2">
                <ActionButton
                  size="sm"
                  variant="secondary"
                  onClick={() => setConfigEditOpen(true)}
                  icon={<Pencil size={12} />}
                  className="hover:border-primary hover:bg-primary/5 hover:text-primary"
                >
                  Edit
                </ActionButton>
                {recordingConfig.has_manual_override && (
                  <ActionButton
                    size="sm"
                    variant="secondary"
                    isPending={resetConfig.isPending}
                    onClick={() => resetConfig.mutate()}
                    icon={<RotateCcw size={12} />}
                    pendingLabel="Resetting…"
                  >
                    Reset override
                  </ActionButton>
                )}
              </div>
              {/* Template is not repeated here — it is always visible in the
                  Details card, which never collapses. */}
              <dl className="space-y-3">
                {recordingConfig.has_manual_override && (
                  <ConfigRow label="Override" value="Manual override active" highlight />
                )}
                {recordingConfig.processing_config?.transcription && (() => {
                  const t = recordingConfig.processing_config!.transcription!;
                  return (
                    <>
                      {t.language     && <ConfigRow label="Language"      value={t.language} />}
                      {t.granularity  && <ConfigRow label="Granularity"   value={t.granularity} />}
                      {t.enable_transcription != null && <ConfigRow label="Transcription" value={t.enable_transcription ? "On" : "Off"} />}
                      {t.enable_topics    != null && <ConfigRow label="Topics"         value={t.enable_topics    ? "On" : "Off"} />}
                      {t.enable_subtitles != null && <ConfigRow label="Subtitles"      value={t.enable_subtitles ? "On" : "Off"} />}
                    </>
                  );
                })()}
                {recordingConfig.output_config && (() => {
                  const o = recordingConfig.output_config!;
                  return (
                    <>
                      {o.auto_upload    != null && <ConfigRow label="Auto-upload"      value={o.auto_upload    ? "On" : "Off"} />}
                      {o.upload_captions != null && <ConfigRow label="Upload captions" value={o.upload_captions ? "On" : "Off"} />}
                      {o.preset_ids?.length      ? <ConfigRow label="Presets"          value={o.preset_ids.join(", ")} /> : null}
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
        <div className={DETAIL_SIDEBAR}>

          {/* Control Panel */}
          <SectionCard title={RECORDING_SECTION.controlPanel} density="compact">
            {isSoftDeleted ? (
              // Restoring is this state's primary action, not a "success" —
              // ActionButton's own primary treatment, no colour override.
              <ActionButton
                disabled={isActing}
                isPending={restoreRec.isPending}
                onClick={() => restoreRec.mutate()}
                icon={<ArchiveRestore size={15} />}
                pendingLabel="Restoring…"
                className="w-full justify-center py-2.5 font-semibold disabled:cursor-not-allowed"
              >
                Restore
              </ActionButton>
            ) : (
              <div className="space-y-3">
                {/* Run / Run with config */}
                <div className={cn(
                  "flex overflow-hidden rounded-xl border",
                  !recording.can_run || isActing
                    ? "border-border opacity-60"
                    : "border-primary"
                )}>
                  <button
                    type="button"
                    disabled={!recording.can_run || isActing}
                    onClick={() => run.mutate()}
                    className={cn(
                      "flex flex-1 items-center justify-center gap-2 px-4 py-2.5 text-sm font-semibold transition-colors disabled:cursor-not-allowed",
                      !recording.can_run || isActing
                        ? "bg-muted text-muted-foreground"
                        : "bg-primary text-white hover:bg-primary-hover"
                    )}
                  >
                    {run.isPending ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      <Play size={14} />
                    )}
                    {run.isPending ? "Running…" : "Run"}
                  </button>
                  <button
                    type="button"
                    disabled={!recording.can_run || isActing}
                    onClick={() => setRunConfigOpen(true)}
                    title="Run with config"
                    className={cn(
                      "flex w-10 shrink-0 items-center justify-center border-l transition-colors disabled:cursor-not-allowed",
                      !recording.can_run || isActing
                        ? "border-border bg-muted text-muted-foreground"
                        : "border-primary-hover bg-primary text-white hover:bg-primary-hover"
                    )}
                  >
                    <Settings2 size={14} />
                  </button>
                </div>

                {/* Pause — only when running */}
                {recording.can_pause && (
                  <ActionButton
                    variant="secondary"
                    isPending={pause.isPending}
                    onClick={() => pause.mutate()}
                    icon={<Pause size={13} />}
                    pendingLabel="Pausing…"
                    className="w-full justify-center py-2"
                  >
                    Pause
                  </ActionButton>
                )}

                {/* Secondary actions. One column until the labels fit side by
                    side — at 320px two columns leave ~75px for the text. */}
                <div className={CONTROL_PANEL_ACTION_GRID}>
                  <button
                    type="button"
                    onClick={() => { setCreateTemplateName(recording.display_name); setCreateTemplateOpen(true); }}
                    className="flex items-center gap-1.5 rounded-xl border border-border bg-card px-3 py-2 text-xs font-medium text-secondary-foreground transition-colors hover:border-primary/40 hover:bg-primary/5 hover:text-primary"
                  >
                    <FilePlus2 size={12} />
                    New template
                  </button>
                  {(recordingConfig?.is_mapped ?? recording.is_mapped) ? (
                    <button
                      type="button"
                      onClick={() => unbindTemplate.mutate()}
                      disabled={unbindTemplate.isPending}
                      className="flex items-center gap-1.5 rounded-xl border border-border bg-card px-3 py-2 text-xs font-medium text-secondary-foreground transition-colors hover:border-foreground/20 hover:text-foreground disabled:opacity-50"
                    >
                      {unbindTemplate.isPending ? <Loader2 size={12} className="animate-spin" /> : <Unlink size={12} />}
                      Unlink
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setBindTemplateOpen(true)}
                      className="flex items-center gap-1.5 rounded-xl border border-border bg-card px-3 py-2 text-xs font-medium text-secondary-foreground transition-colors hover:border-primary/40 hover:bg-primary/5 hover:text-primary"
                    >
                      <Link2 size={12} />
                      Link template
                    </button>
                  )}
                </div>

                {/* Share */}
                <div>
                  <ActionButton
                    variant="secondary"
                    onClick={() => setShareOpen(true)}
                    icon={<Share2 size={13} />}
                    className={cn(
                      "w-full justify-center py-2",
                      shareToken
                        ? "border-primary/40 bg-primary/5 text-primary hover:bg-primary/10"
                        : "hover:border-primary/40 hover:bg-primary/5 hover:text-primary"
                    )}
                  >
                    {shareToken ? "Manage share" : "Share"}
                  </ActionButton>
                </div>

                {/* Destructive actions — kept out of the routine grid above so
                    Delete is not one mis-click away from "Link template". */}
                <div className="space-y-1.5 border-t border-border pt-3">
                  <div className={CONTROL_PANEL_ACTION_GRID}>
                    <button
                      type="button"
                      disabled={isActing}
                      onClick={() => setResetConfirm(true)}
                      className="flex items-center gap-1.5 rounded-xl border border-border bg-card px-3 py-2 text-xs font-medium text-secondary-foreground transition-colors hover:border-foreground/20 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {resetRec.isPending ? <Loader2 size={12} className="animate-spin" /> : <RotateCcw size={12} />}
                      Reset
                    </button>
                    <button
                      type="button"
                      disabled={isActing}
                      onClick={() => setDeleteConfirm(true)}
                      className="flex items-center gap-1.5 rounded-xl border border-danger-fg/40 bg-card px-3 py-2 text-xs font-medium text-danger-fg transition-colors hover:bg-danger-fg/10 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <Trash2 size={12} />
                      Delete
                    </button>
                  </div>
                </div>
              </div>
            )}
          </SectionCard>

          {/* Details — the recording's own attributes. Not collapsible: these
              used to sit at the bottom of the collapsed Configuration card, so
              nothing about the recording was readable without a click. */}
          <SectionCard title={RECORDING_SECTION.details} density="compact">
            <dl className="space-y-2">
              <SidebarInfoRow label="ID"       value={`#${recording.id}`} />
              <SidebarInfoRow label="Template" value={templateDetailNavValue} />
              {recording.source?.source_type && (
                <SidebarInfoRow label="Source"   value={recording.source.source_type} />
              )}
              <SidebarInfoRow label="Date"     value={formatDate(recording.start_time)} />
              {recording.duration > 0 && (
                <SidebarInfoRow label="Duration" value={formatDuration(recording.duration) ?? "—"} />
              )}
              {recording.video_file_size ? (
                <SidebarInfoRow label="File size" value={formatFileSize(recording.video_file_size)} />
              ) : null}
            </dl>
          </SectionCard>

          {/* Publications */}
          <SectionCard
            title={RECORDING_SECTION.publications}
            density="compact"
            action={
              recording.upload_summary && recording.upload_summary.total > 0 ? (
                <span className={cn(
                  "rounded-full px-2 py-0.5 text-xs font-medium tabular-nums",
                  recording.upload_summary.uploaded === recording.upload_summary.total
                    ? "bg-success-fg/10 text-success-fg"
                    : recording.upload_summary.failed > 0
                      ? "bg-danger-fg/10 text-danger-fg"
                      : "bg-muted text-muted-foreground"
                )}>
                  {recording.upload_summary.uploaded}/{recording.upload_summary.total}
                </span>
              ) : undefined
            }
          >
            {recording.outputs.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                No platforms configured. Add presets and run the recording.
              </p>
            ) : (
              <div className="divide-y divide-muted">
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
          </SectionCard>

          {/* Downloads */}
          {artefacts.length > 0 && (
            <SectionCard title={RECORDING_SECTION.files} density="compact">
              {mediaDownloadError && (
                <div role="alert" className="mb-2 rounded-lg border border-danger-fg/20 bg-danger-fg/10 px-3 py-2 text-xs text-danger-fg">
                  {mediaDownloadError}
                </div>
              )}
              <ArtefactList items={artefacts} />
            </SectionCard>
          )}

          {/* Pipeline — collapsible, auto-expands when processing is active */}
          <PipelineCard stages={allPipelineStages} durationSeconds={recording.pipeline_duration_seconds} defaultOpen={recording.on_air} />
        </div>
      </div>

      <ShareModal
        open={shareOpen}
        onClose={() => setShareOpen(false)}
        recordingId={recording.id}
        initialToken={shareToken}
        onTokenChange={setShareTokenOverride}
        onToast={(msg, variant) => showToast(variant === "error" ? "error" : "success", msg)}
      />

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
        description="The recording will return to INITIALIZED status."
        confirmLabel="Reset"
        cancelLabel="Cancel"
        onConfirm={() => { setResetConfirm(false); resetRec.mutate(); }}
        onCancel={() => setResetConfirm(false)}
      >
        <label className="flex items-center gap-2 text-sm text-secondary-foreground select-none cursor-pointer">
          <input
            type="checkbox"
            checked={resetDeleteFiles}
            onChange={(e) => setResetDeleteFiles(e.target.checked)}
            className="rounded border-border text-primary focus:ring-primary/30"
          />
          Delete processed files (video, audio, transcription)
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
        label="Bind template"
        panelClassName="max-w-sm"
      >
        <div className="p-6">
          <h2 className="mb-4 text-sm font-semibold text-foreground">Bind to template</h2>
          {bindTemplate.isError && (
            <p className="mb-3 text-xs text-danger-fg">
              {(bindTemplate.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Error"}
            </p>
          )}
          <div className="relative mb-3">
            <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              aria-label="Search templates"
              placeholder="Search templates…"
              value={bindTemplateSearch}
              onChange={(e) => setBindTemplateSearch(e.target.value)}
              className="w-full rounded-xl border border-input bg-card py-2 pl-8 pr-3 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/30"
            />
          </div>
          <div className="max-h-64 space-y-1.5 overflow-y-auto">
            {(() => {
              const allItems = bindTemplatesData?.items ?? [];
              const filtered = bindTemplateSearch.trim()
                ? allItems.filter((t) => t.name.toLowerCase().includes(bindTemplateSearch.toLowerCase()))
                : allItems;
              if (filtered.length === 0) {
                return <p className="py-6 text-center text-sm text-muted-foreground">{allItems.length === 0 ? "No templates" : "Nothing found"}</p>;
              }
              return filtered.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  disabled={bindTemplate.isPending}
                  onClick={() => { bindTemplate.mutate(t.id); setBindTemplateSearch(""); }}
                  className="flex w-full items-center justify-between gap-2 rounded-xl border border-border bg-card px-3 py-2.5 text-left text-sm font-medium text-foreground transition-colors hover:border-primary hover:bg-primary/5 disabled:opacity-50"
                >
                  <span className="min-w-0 truncate">{t.name}</span>
                  <Link2 size={13} className="shrink-0 text-muted-foreground" />
                </button>
              ));
            })()}
          </div>
          <div className="flex justify-end pt-4">
            <ActionButton variant="secondary" onClick={() => { setBindTemplateOpen(false); setBindTemplateSearch(""); }}>
              Cancel
            </ActionButton>
          </div>
        </div>
      </Modal>

      {/* Create template modal */}
      <Modal
        open={createTemplateOpen}
        onClose={() => setCreateTemplateOpen(false)}
        label="Create template from recording"
        panelClassName="max-w-sm"
      >
        <div className="p-6">
          <h2 className="mb-4 text-sm font-semibold text-foreground">Create template from recording</h2>
          <div className="space-y-3">
            <div className="space-y-1">
              <label htmlFor="new-template-name" className="text-xs font-medium text-muted-foreground">
                Template name
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
                placeholder="Template name"
                className="w-full rounded-xl border border-input bg-card px-3 py-2 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/30"
              />
            </div>
            {createTemplate.isError && (
              <p className="text-xs text-danger-fg">
                {(createTemplate.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Error"}
              </p>
            )}
            <div className="flex justify-end gap-2 pt-1">
              <ActionButton variant="secondary" onClick={() => setCreateTemplateOpen(false)}>
                Cancel
              </ActionButton>
              <ActionButton
                disabled={!createTemplateName.trim()}
                isPending={createTemplate.isPending}
                isSuccess={createTemplate.isSuccess}
                onClick={() => createTemplate.mutate(createTemplateName.trim())}
                icon={<FilePlus2 size={14} />}
                pendingLabel="Creating…"
                className="font-semibold"
              >
                Create
              </ActionButton>
            </div>
          </div>
        </div>
      </Modal>

      {toast && (
        <Toast key={toast.serial} type={toast.type} message={toast.msg} exiting={toast.exiting} onDismiss={dismissToast} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Loading skeleton — reuses the same cards and layout tokens as the page.
// ---------------------------------------------------------------------------

function RecordingDetailSkeleton() {
  return (
    <div className={PAGE_ROOT} aria-busy="true">
      <Skeleton className="mb-2 h-4 w-24" aria-hidden />
      <div className="mb-5 flex min-h-[2.5rem] flex-wrap items-center gap-x-3 gap-y-2">
        <Skeleton className="h-8 min-w-0 flex-1 max-w-xl" />
        <Skeleton className="h-6 w-24 shrink-0 rounded-full" />
      </div>

      <div className={cn(DETAIL_COLUMNS, "pointer-events-none")}>
        <div className={DETAIL_MAIN}>
          <SectionCard title={RECORDING_SECTION.video} density="compact">
            <Skeleton className="aspect-video w-full rounded-xl" />
          </SectionCard>

          <CollapsibleCard title={RECORDING_SECTION.description} open={false}>
            {null}
          </CollapsibleCard>

          <CollapsibleCard title={RECORDING_SECTION.chapters} open>
            <div className="space-y-3">
              <Skeleton className="h-3 w-2/5" />
              <Skeleton className="h-3 w-full" />
              <Skeleton className="h-3 w-4/5" />
              <div className="space-y-2 pt-2">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-8 w-full rounded-lg" />
                ))}
              </div>
            </div>
          </CollapsibleCard>

          <CollapsibleCard title={RECORDING_SECTION.configuration} open={false}>
            {null}
          </CollapsibleCard>
        </div>

        <div className={DETAIL_SIDEBAR}>
          <SectionCard title={RECORDING_SECTION.controlPanel} density="compact">
            <div className="space-y-3">
              <Skeleton className="h-[2.625rem] w-full rounded-xl" />
              <div className={CONTROL_PANEL_ACTION_GRID}>
                <Skeleton className="h-9 rounded-xl" />
                <Skeleton className="h-9 rounded-xl" />
              </div>
              <Skeleton className="h-9 w-full rounded-xl" />
              <div className="space-y-1.5 border-t border-border pt-3">
                <div className={CONTROL_PANEL_ACTION_GRID}>
                  <Skeleton className="h-9 rounded-xl" />
                  <Skeleton className="h-9 rounded-xl" />
                </div>
              </div>
            </div>
          </SectionCard>

          <SectionCard title={RECORDING_SECTION.details} density="compact">
            <dl className="space-y-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="flex justify-between gap-2">
                  <Skeleton className="h-3 w-14" />
                  <Skeleton className="h-3 w-20" />
                </div>
              ))}
            </dl>
          </SectionCard>

          <SectionCard title={RECORDING_SECTION.publications} density="compact">
            <Skeleton className="h-3 w-full max-w-xs" />
          </SectionCard>

          <CollapsibleCard
            title={RECORDING_SECTION.pipeline}
            open={false}
            badge={<Skeleton className="h-5 w-10 rounded-full" />}
          >
            {null}
          </CollapsibleCard>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helper row components
// ---------------------------------------------------------------------------

function PipelineCard({ stages, durationSeconds, defaultOpen }: { stages: ProcessingStage[]; durationSeconds: number | null; defaultOpen?: boolean }) {
  const completed = stages.filter((s) => s.status === "COMPLETED" || s.status === "SKIPPED").length;
  const hasFailed = stages.some((s) => s.failed);
  const total = stages.length;

  // A failed pipeline is the main reason anyone opens this card, and the page
  // polls every few seconds, so the failure usually lands *after* the first
  // render. Deriving `open` instead of seeding state means a stage that fails
  // mid-poll still reveals itself; once the reader toggles the card, their
  // choice wins.
  const [userToggled, setUserToggled] = useState<boolean | null>(null);
  const open = userToggled ?? (defaultOpen || hasFailed);

  return (
    <CollapsibleCard
      title={RECORDING_SECTION.pipeline}
      open={open}
      onOpenChange={setUserToggled}
      badge={
        <>
          {total > 0 && (
            <span className={cn(
              "rounded-full px-2 py-0.5 text-xs font-medium tabular-nums",
              hasFailed ? "bg-danger-fg/10 text-danger-fg" : completed === total ? "bg-success-fg/10 text-success-fg" : "bg-muted text-muted-foreground"
            )}>
              {completed}/{total}
            </span>
          )}
          {durationSeconds != null && durationSeconds > 0 && (
            <span className="text-xs tabular-nums text-muted-foreground">~{Math.round(durationSeconds)}s</span>
          )}
        </>
      }
    >
      <PipelineStageList stages={stages} />
    </CollapsibleCard>
  );
}

function SidebarInfoRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex justify-between gap-2">
      <dt className="shrink-0 text-xs text-muted-foreground">{label}</dt>
      <dd
        className="min-w-0 truncate text-right text-xs font-medium text-foreground"
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
      <dt className="shrink-0 text-sm text-muted-foreground">{label}</dt>
      <dd
        className={cn(
          "min-w-0 max-w-[70%] text-right text-sm",
          highlight ? "font-medium text-warning-fg" : "text-foreground",
          mono && "font-mono text-xs"
        )}
      >
        {value}
      </dd>
    </div>
  );
}
