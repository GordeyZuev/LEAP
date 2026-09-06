"use client";

import { useEffect, useId, useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ExternalLink, Eye, Loader2, Play, Save, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { runToastMessage, type RunOperationResponse } from "@/lib/run-response";
import { useToast } from "@/hooks/use-toast";
import { apiClient } from "@/api/client";
import { Modal } from "@/components/ui/modal";
import { ActionButton } from "@/components/ui/action-button";
import { FILTER_LABEL } from "@/lib/filter-field-classes";
import { NativeSelect } from "@/components/ui/native-select";
import { Field } from "@/components/ui/field";
import { NumberInput } from "@/components/ui/number-input";
import { SegmentedField } from "@/components/ui/segmented-field";
import { PlaylistPicker } from "@/components/playlists/playlist-picker";
import { Toggle } from "@/components/ui/toggle";
import {
  TemplateField,
  YouTubeFields,
  VkFields,
  YandexDiskFields,
  DEFAULT_YOUTUBE_FIELDS,
  DEFAULT_VK_FIELDS,
  DEFAULT_YANDEX_DISK_FIELDS,
  youtubeFieldsFromApi,
  vkFieldsFromApi,
  vkFieldsToApi,
  yandexFieldsFromApi,
  type YouTubeFieldsValue,
  type VkFieldsValue,
  type YandexDiskFieldsValue,
} from "@/components/platforms/platform-fields";
import {
  DisplayConfigFields,
  type DisplayConfig,
  defaultTopicsDisplay,
  defaultQuestionsDisplay,
  toDisplayPayload,
  fromDisplayPayload,
  appendDisplayConfigPreviewBody,
} from "@/components/platforms/display-config-fields";
import { ThumbnailPicker } from "@/components/platforms/thumbnail-picker";
import {
  MetadataPreviewResultBox,
  type MetadataRenderPreviewData,
} from "@/components/platforms/metadata-render-preview";
import { TagInput } from "@/components/ui/tag-input";
import { useGranularities, useLanguages } from "@/hooks/use-references";
import { formatBaseTemplateLabel } from "@/lib/base-template";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface TemplateItem { id: number; name: string; is_default?: boolean }
interface TemplateListResponse { items: TemplateItem[]; total: number }
interface PresetItem { id: number; name: string; platform: string; credential_id?: number | null }
interface PresetListResponse { items: PresetItem[]; total: number }

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
      allow_errors?: boolean;
      questions_count?: number;
      vocabulary?: string[];
    };
  } | null;
  output_config: {
    auto_upload?: boolean;
    upload_captions?: boolean;
    preset_ids?: number[];
    playlist_ids?: number[];
  } | null;
  metadata_config: {
    title_template?: string;
    description_template?: string;
    thumbnail_name?: string;
    topics_display?: Record<string, unknown>;
    questions_display?: Record<string, unknown>;
    youtube?: {
      privacy?: string;
      playlist_id?: string;
      thumbnail_name?: string;
      title_template?: string;
      description_template?: string;
      category_id?: string | number;
      tags?: string[];
      made_for_kids?: boolean;
    };
    vk?: {
      album_id?: string | number;
      group_id?: number;
      thumbnail_name?: string;
      title_template?: string;
      description_template?: string;
      privacy_view?: number;
      privacy_comment?: number;
      wallpost?: boolean;
    };
    yandex_disk?: {
      folder_path_template?: string;
      filename_template?: string;
      overwrite?: boolean;
      publish?: boolean;
    };
  } | null;
}

export interface RunConfigModalProps {
  open: boolean;
  onClose: () => void;
  mode: "single" | "bulk";
  recordingId?: number;
  recordingName?: string;
  recordingIds?: number[];
  /** Bulk mode only — shown so the user can see what they are about to run. */
  recordingNames?: string[];
  onSuccess?: () => void;
  /** "run" launches the pipeline; "save" persists per-recording config via
   *  PATCH /config without running (single mode only). */
  submitMode?: "run" | "save";
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// SectionToggle
// ---------------------------------------------------------------------------

/**
 * One override section: a switch that decides whether this run overrides the
 * template at all, plus a disclosure for the fields themselves.
 *
 * The switch is the primary control and drives the whole section — turning it on
 * expands the body, and turning it off collapses the fields back out of the way,
 * so "inherit from template" is the visible resting state.
 *
 * The body is a real `<fieldset disabled>`. It used to be styled with
 * `pointer-events-none opacity-50`, which blocks the mouse but not the keyboard:
 * Tab still reached every control in a section the user had switched off, they
 * still operated, and screen readers still announced them as enabled.
 */
function OverrideSection({
  title,
  switchLabel,
  enabled,
  onEnabledChange,
  open,
  onOpenChange,
  enabledHint,
  disabledHint = "inherits effective config",
  children,
}: {
  title: string;
  /** Accessible name for the switch — the title reads badly with "Override" glued on. */
  switchLabel: string;
  enabled: boolean;
  onEnabledChange: (v: boolean) => void;
  open: boolean;
  onOpenChange: (v: boolean) => void;
  enabledHint?: string;
  disabledHint?: string;
  children: React.ReactNode;
}) {
  const titleId = useId();
  return (
    <div className="rounded-xl border border-border bg-background">
      <div className="flex items-center gap-3 px-4 py-3">
        <Toggle
          label={switchLabel}
          labelHidden
          checked={enabled}
          onChange={(v) => {
            onEnabledChange(v);
            if (v) onOpenChange(true);
            else onOpenChange(false);
          }}
        />
        <button
          type="button"
          onClick={() => onOpenChange(!open)}
          aria-expanded={open}
          className="flex flex-1 items-center gap-2 text-left"
        >
          <span id={titleId} className="text-sm font-semibold text-foreground">{title}</span>
          <span className="text-xs text-muted-foreground">
            {enabled ? (enabledHint ?? "overridden for this run") : disabledHint}
          </span>
          <ChevronDown
            size={16}
            className={cn("ms-auto shrink-0 text-muted-foreground transition-transform", open && "rotate-180")}
          />
        </button>
      </div>

      {open && (
        <fieldset
          disabled={!enabled}
          className="space-y-4 border-t border-border px-4 pb-4 pt-4 disabled:opacity-50"
        >
          <legend className="sr-only">{title}</legend>
          {children}
        </fieldset>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// PlatformSection — collapsible sub-accordion for per-platform metadata
// ---------------------------------------------------------------------------

function PlatformSection({ label, children }: { label: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-xl border border-border bg-card">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium text-secondary-foreground hover:text-foreground"
      >
        {label}
        <ChevronDown
          size={16}
          className={cn("shrink-0 text-muted-foreground transition-transform", open && "rotate-180")}
        />
      </button>
      {open && (
        <div className="space-y-3 border-t border-border px-4 pb-4 pt-3">
          {children}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function RunConfigModal({
  open,
  onClose,
  mode,
  recordingId,
  recordingName,
  recordingIds,
  recordingNames,
  onSuccess,
  submitMode = "run",
}: RunConfigModalProps) {
  const qc = useQueryClient();
  const { show: showToast } = useToast();
  const isSave = submitMode === "save";
  const titleId = useId();
  const { data: languages = [] } = useLanguages();
  const { data: granularities = [] } = useGranularities();

  // ── Template ──────────────────────────────────────────────────────────────
  const [templateOpen, setTemplateOpen] = useState(true);
  const [templateId, setTemplateId] = useState<number | null>(null);
  const [bindTemplate, setBindTemplate] = useState(false);

  // ── Processing ────────────────────────────────────────────────────────────
  const [processingEnabled, setProcessingEnabled] = useState(false);
  const [processingOpen, setProcessingOpen] = useState(false);
  const [language, setLanguage] = useState("ru");
  const [granularity, setGranularity] = useState("long");
  const [enableTranscription, setEnableTranscription] = useState(true);
  const [enableTopics, setEnableTopics] = useState(true);
  const [enableSubtitles, setEnableSubtitles] = useState(true);
  const [allowErrors, setAllowErrors] = useState(false);
  const [questionsCount, setQuestionsCount] = useState(3);
  const [vocabulary, setVocabulary] = useState<string[]>([]);

  // ── Output ────────────────────────────────────────────────────────────────
  const [outputEnabled, setOutputEnabled] = useState(false);
  const [outputOpen, setOutputOpen] = useState(false);
  const [autoUpload, setAutoUpload] = useState(false);
  const [uploadCaptions, setUploadCaptions] = useState(true);
  const [selectedPresetIds, setSelectedPresetIds] = useState<number[]>([]);
  const [selectedPlaylistIds, setSelectedPlaylistIds] = useState<number[]>([]);

  // ── Metadata ──────────────────────────────────────────────────────────────
  const [metadataEnabled, setMetadataEnabled] = useState(false);
  const [metadataOpen, setMetadataOpen] = useState(false);
  const [titleTemplate, setTitleTemplate] = useState("");
  const [descriptionTemplate, setDescriptionTemplate] = useState("");
  const [globalThumbnail, setGlobalThumbnail] = useState("");
  const [thumbnailTouched, setThumbnailTouched] = useState(false);
  const [topicsDisplay, setTopicsDisplay] = useState<DisplayConfig>(() => defaultTopicsDisplay());
  const [questionsDisplay, setQuestionsDisplay] = useState<DisplayConfig>(() => defaultQuestionsDisplay());
  const [ytFields, setYtFields] = useState<YouTubeFieldsValue>({ ...DEFAULT_YOUTUBE_FIELDS });
  const [vkFields, setVkFields] = useState<VkFieldsValue>({ ...DEFAULT_VK_FIELDS });
  const [ydFields, setYdFields] = useState<YandexDiskFieldsValue>({ ...DEFAULT_YANDEX_DISK_FIELDS });

  const [metadataPreview, setMetadataPreview] = useState<MetadataRenderPreviewData | null>(null);
  const [metadataPreviewLoading, setMetadataPreviewLoading] = useState(false);

  // ── Reference data ────────────────────────────────────────────────────────
  const { data: templatesData } = useQuery<TemplateListResponse>({
    queryKey: ["templates-dropdown"],
    queryFn: async () => (await apiClient.get<TemplateListResponse>("/templates?per_page=100")).data,
    enabled: open,
  });

  const { data: defaultTemplate } = useQuery<TemplateItem>({
    queryKey: ["default-template"],
    queryFn: async () => (await apiClient.get<TemplateItem>("/templates/default")).data,
    enabled: open,
  });

  const namedTemplates = useMemo(
    () => (templatesData?.items ?? []).filter((t) => !t.is_default),
    [templatesData?.items],
  );

  const { data: presetsData } = useQuery<PresetListResponse>({
    queryKey: ["presets-dropdown"],
    queryFn: async () => (await apiClient.get<PresetListResponse>("/presets?per_page=100")).data,
    enabled: open,
  });

  const { data: existingConfig, isLoading: configLoading } = useQuery<RecordingConfigResponse>({
    queryKey: ["recording-config", recordingId],
    queryFn: async () =>
      (await apiClient.get<RecordingConfigResponse>(`/recordings/${recordingId}/config`)).data,
    enabled: open && mode === "single" && !!recordingId,
  });

  const boundTemplateId = useMemo(() => {
    const id = existingConfig?.template_id ?? null;
    if (id == null) return null;
    if (defaultTemplate?.id != null && id === defaultTemplate.id) return null;
    if (templatesData?.items.some((t) => t.is_default && t.id === id)) return null;
    return id;
  }, [existingConfig?.template_id, defaultTemplate?.id, templatesData?.items]);

  const boundTemplateName = boundTemplateId != null ? existingConfig?.template_name : null;
  const baseTemplateLabel = formatBaseTemplateLabel(defaultTemplate?.name);

  const openTemplateId = useMemo(() => {
    if (templateId != null) return templateId;
    if (boundTemplateId != null) return boundTemplateId;
    return defaultTemplate?.id ?? null;
  }, [templateId, boundTemplateId, defaultTemplate?.id]);

  // ── Mutation ──────────────────────────────────────────────────────────────
  const runMutation = useMutation({
    mutationFn: async () => {
      const body: Record<string, unknown> = {};

      if (templateId) {
        body.template_id = templateId;
        body.bind_template = bindTemplate;
      }

      if (processingEnabled) {
        body.processing_config = {
          transcription: {
            enable_transcription: enableTranscription,
            enable_topics: enableTopics,
            enable_subtitles: enableSubtitles,
            language,
            granularity,
            allow_errors: allowErrors,
            questions_count: questionsCount,
            ...(vocabulary.length > 0 ? { vocabulary } : {}),
          },
        };
      }

      const outputCfg: Record<string, unknown> = {};
      if (outputEnabled) {
        outputCfg.auto_upload = autoUpload;
        outputCfg.upload_captions = uploadCaptions;
        if (selectedPresetIds.length > 0) outputCfg.preset_ids = selectedPresetIds;
      }
      if (selectedPlaylistIds.length > 0) outputCfg.playlist_ids = selectedPlaylistIds;
      if (Object.keys(outputCfg).length > 0) body.output_config = outputCfg;

      if (metadataEnabled) {
        const meta: Record<string, unknown> = {};
        if (titleTemplate) meta.title_template = titleTemplate;
        if (descriptionTemplate) meta.description_template = descriptionTemplate;
        const tdPayload = toDisplayPayload(topicsDisplay, "topics");
        if (tdPayload) meta.topics_display = tdPayload;
        const qdPayload = toDisplayPayload(questionsDisplay, "questions");
        if (qdPayload) meta.questions_display = qdPayload;
        if (globalThumbnail || thumbnailTouched) meta.thumbnail_name = globalThumbnail;

        const yt: Record<string, unknown> = {};
        if (ytFields.privacy) yt.privacy = ytFields.privacy;
        if (ytFields.playlist_id) yt.playlist_id = ytFields.playlist_id;
        if (ytFields.thumbnail_name) yt.thumbnail_name = ytFields.thumbnail_name;
        if (ytFields.title_template) yt.title_template = ytFields.title_template;
        if (ytFields.description_template) yt.description_template = ytFields.description_template;
        if (ytFields.category_id) yt.category_id = ytFields.category_id;
        if (ytFields.tags.length > 0) yt.tags = ytFields.tags;
        if (ytFields.made_for_kids) yt.made_for_kids = true;
        if (Object.keys(yt).length > 0) meta.youtube = yt;

        const vk = vkFieldsToApi(vkFields, { sparseBools: true });
        if (Object.keys(vk).length > 0) meta.vk = vk;

        const yd: Record<string, unknown> = {};
        if (ydFields.folder_path_template) yd.folder_path_template = ydFields.folder_path_template;
        if (ydFields.filename_template) yd.filename_template = ydFields.filename_template;
        if (ydFields.overwrite) yd.overwrite = true;
        if (ydFields.publish) yd.publish = true;
        if (Object.keys(yd).length > 0) meta.yandex_disk = yd;

        if (Object.keys(meta).length > 0) body.metadata_config = meta;
      }

      if (isSave) {
        const patch: Record<string, unknown> = {};
        if (body.processing_config) patch.processing_config = body.processing_config;
        if (body.output_config) patch.output_config = body.output_config;
        if (body.metadata_config) {
          patch.metadata_config = body.metadata_config;
        } else if (thumbnailTouched) {
          patch.metadata_config = { thumbnail_name: globalThumbnail };
        }
        return apiClient.patch(`/recordings/${recordingId}/config`, patch);
      }

      if (mode === "single") {
        return apiClient.post<RunOperationResponse>(`/recordings/${recordingId}/run`, body);
      }
      return apiClient.post("/recordings/bulk/run", {
        recording_ids: recordingIds,
        ...body,
      });
    },
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["recordings"] });
      qc.invalidateQueries({ queryKey: ["playlists"] });
      qc.invalidateQueries({ queryKey: ["playlist"] });
      qc.invalidateQueries({ queryKey: ["playlist-items"] });
      if (recordingId) {
        qc.invalidateQueries({ queryKey: ["recording", String(recordingId)] });
        qc.invalidateQueries({ queryKey: ["recording-config", recordingId] });
      }
      if (!isSave && mode === "single" && res && "data" in res) {
        const { kind, text } = runToastMessage((res as { data: RunOperationResponse }).data);
        showToast(kind, text);
      }
      onSuccess?.();
      onClose();
    },
  });

  // ── Reset to defaults on open ─────────────────────────────────────────────
  useEffect(() => {
    if (!open) return;
    /* eslint-disable react-hooks/set-state-in-effect */
    setTemplateOpen(true);
    setTemplateId(null);
    setBindTemplate(false);
    setProcessingEnabled(false);
    setProcessingOpen(false);
    setLanguage("ru");
    setGranularity("long");
    setEnableTranscription(true);
    setEnableTopics(true);
    setEnableSubtitles(true);
    setAllowErrors(false);
    setQuestionsCount(3);
    setVocabulary([]);
    setOutputEnabled(false);
    setOutputOpen(false);
    setAutoUpload(false);
    setUploadCaptions(true);
    setSelectedPresetIds([]);
    setSelectedPlaylistIds([]);
    setMetadataEnabled(false);
    setMetadataOpen(false);
    setTitleTemplate("");
    setDescriptionTemplate("");
    setGlobalThumbnail("");
    setThumbnailTouched(false);
    setTopicsDisplay(defaultTopicsDisplay());
    setQuestionsDisplay(defaultQuestionsDisplay());
    setYtFields({ ...DEFAULT_YOUTUBE_FIELDS });
    setVkFields({ ...DEFAULT_VK_FIELDS });
    setYdFields({ ...DEFAULT_YANDEX_DISK_FIELDS });
    setMetadataPreview(null);
    setMetadataPreviewLoading(false);
    /* eslint-enable react-hooks/set-state-in-effect */
    runMutation.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // ── Pre-fill effective values; override toggles stay off until user enables them ──
  useEffect(() => {
    if (!open || !existingConfig) return;
    /* eslint-disable react-hooks/set-state-in-effect */
    const t = existingConfig.processing_config?.transcription;
    if (t) {
      if (t.language != null) setLanguage(t.language);
      if (t.granularity != null) setGranularity(t.granularity);
      if (t.enable_transcription != null) setEnableTranscription(t.enable_transcription);
      if (t.enable_topics != null) setEnableTopics(t.enable_topics);
      if (t.enable_subtitles != null) setEnableSubtitles(t.enable_subtitles);
      if (t.allow_errors != null) setAllowErrors(t.allow_errors);
      if (t.questions_count != null) setQuestionsCount(t.questions_count);
      if (t.vocabulary != null) setVocabulary(t.vocabulary);
    }

    const oc = existingConfig.output_config;
    if (oc) {
      if (oc.auto_upload != null) setAutoUpload(oc.auto_upload);
      if (oc.upload_captions != null) setUploadCaptions(oc.upload_captions);
      if (oc.preset_ids) setSelectedPresetIds(oc.preset_ids);
      if (oc.playlist_ids) setSelectedPlaylistIds(oc.playlist_ids);
    }

    const mc = existingConfig.metadata_config;
    if (mc) {
      if (mc.title_template) setTitleTemplate(mc.title_template);
      if (mc.description_template) setDescriptionTemplate(mc.description_template);
      if (mc.thumbnail_name) setGlobalThumbnail(mc.thumbnail_name);
      setTopicsDisplay(fromDisplayPayload(mc.topics_display, "topics"));
      setQuestionsDisplay(fromDisplayPayload(mc.questions_display, "questions"));
      if (mc.youtube) setYtFields(youtubeFieldsFromApi(mc.youtube));
      if (mc.vk) setVkFields(vkFieldsFromApi(mc.vk));
      if (mc.yandex_disk) setYdFields(yandexFieldsFromApi(mc.yandex_disk));
    }
    if (isSave) setMetadataOpen(true);
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [open, existingConfig, isSave]);

  const overrideEnabledHint = isSave ? "saved on this recording" : undefined;
  const count = mode === "bulk" ? (recordingIds?.length ?? 0) : 1;
  const title = isSave
    ? `Edit configuration${recordingName ? `: "${recordingName}"` : recordingId ? ` #${recordingId}` : ""}`
    : mode === "single"
      ? `Run with config${recordingName ? `: "${recordingName}"` : recordingId ? ` #${recordingId}` : ""}`
      : `Bulk run ${count} recording${count !== 1 ? "s" : ""} with config`;

  const runError =
    (runMutation.error as { response?: { data?: { detail?: string } } } | null)?.response?.data?.detail ??
    (runMutation.isError ? (isSave ? "Failed to save" : "Failed to run") : null);

  function togglePreset(id: number) {
    setSelectedPresetIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }

  const presetsByPlatform = (presetsData?.items ?? []).reduce<Record<string, PresetItem[]>>(
    (acc, p) => { (acc[p.platform] = acc[p.platform] ?? []).push(p); return acc; },
    {}
  );

  const yandexBrowseCredentialId = useMemo(() => {
    for (const pid of selectedPresetIds) {
      const preset = presetsData?.items.find((p) => p.id === pid);
      if (preset?.platform === "yandex_disk" && preset.credential_id != null) {
        return preset.credential_id;
      }
    }
    return "" as const;
  }, [selectedPresetIds, presetsData?.items]);

  async function handleMetadataPreview() {
    setMetadataPreviewLoading(true);
    setMetadataPreview(null);
    try {
      const body: Record<string, unknown> = {};
      if (mode === "single" && recordingId != null) {
        body.recording_id = recordingId;
      }
      const effectiveTemplateId = templateId ?? (mode === "single" ? boundTemplateId : null);
      if (effectiveTemplateId != null) {
        body.template_id = effectiveTemplateId;
      }
      if (metadataEnabled) {
        const tt = titleTemplate.trim();
        const dt = descriptionTemplate.trim();
        if (tt) body.title_template = titleTemplate;
        if (dt) body.description_template = descriptionTemplate;
        const folder = ydFields.folder_path_template?.trim();
        const fname = ydFields.filename_template?.trim();
        if (folder) body.folder_path_template = folder;
        if (fname) body.filename_template = fname;
        appendDisplayConfigPreviewBody(body, topicsDisplay, questionsDisplay);
      }

      const res = await apiClient.post<MetadataRenderPreviewData>("/templates/render-preview", body);
      setMetadataPreview(res.data);
    } catch {
      setMetadataPreview(null);
    } finally {
      setMetadataPreviewLoading(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      labelledBy={titleId}
      panelClassName="flex max-h-[92vh] w-full sm:max-w-2xl flex-col bg-card"
    >
      <>
        {/* Header */}
        <div className="flex shrink-0 items-center justify-between border-b border-border px-6 py-4">
          <h2 id={titleId} className="min-w-0 truncate text-sm font-semibold text-foreground">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close dialog"
            className="ml-4 shrink-0 text-muted-foreground hover:text-secondary-foreground transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Body. Sections are already background-separated cards, so spacing
            carries the grouping and the divider lines are just noise. */}
        <div className="flex-1 space-y-3 overflow-y-auto px-6 py-4">
          {configLoading ? (
            <div className="flex items-center justify-center gap-2 py-14 text-sm text-muted-foreground">
              <Loader2 size={16} className="animate-spin text-primary" />
              Loading configuration…
            </div>
          ) : <>

          {isSave && (
            <div className="rounded-xl border border-border bg-background px-4 py-4">
              <ThumbnailPicker
                label="Thumbnail"
                value={globalThumbnail}
                onChange={(name) => {
                  setGlobalThumbnail(name);
                  setThumbnailTouched(true);
                }}
              />
            </div>
          )}

          {/* Bulk runs used to say only "12 recordings" — name them, so the
              user can see what they are about to launch. */}
          {mode === "bulk" && !!recordingNames?.length && (
            <details className="rounded-xl border border-border bg-background px-4 py-3">
              <summary className="cursor-pointer text-sm font-medium text-secondary-foreground marker:text-muted-foreground">
                {count} recording{count !== 1 ? "s" : ""} selected
              </summary>
              <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
                {recordingNames.map((name, i) => (
                  <li key={`${name}-${i}`} className="truncate" title={name}>{name}</li>
                ))}
              </ul>
            </details>
          )}

          {/* ── Template ────────────────────────────────────────────────── */}
          {!isSave && (
          <div className="rounded-xl border border-border bg-background">
            <button
              type="button"
              onClick={() => setTemplateOpen((v) => !v)}
              aria-expanded={templateOpen}
              className="flex w-full items-center gap-2 px-4 py-3 text-left"
            >
              <span className="text-sm font-semibold text-foreground">Template</span>
              <span className="text-xs text-muted-foreground">
                {templateId
                  ? templatesData?.items.find((t) => t.id === templateId)?.name ?? "selected"
                  : boundTemplateName ?? baseTemplateLabel}
              </span>
              <ChevronDown
                size={16}
                className={cn("ms-auto shrink-0 text-muted-foreground transition-transform", templateOpen && "rotate-180")}
              />
            </button>

            {templateOpen && (
              <div className="space-y-4 border-t border-border px-4 pb-4 pt-4">
                <Field label="Template to use for this run">
                  <div className="flex items-center gap-2">
                    <NativeSelect
                      wrapperClassName="min-w-0 flex-1"
                      value={templateId ?? ""}
                      onChange={(e) => setTemplateId(e.target.value ? Number(e.target.value) : null)}
                    >
                      <option value="">{baseTemplateLabel}</option>
                      {namedTemplates.map((t) => (
                        <option key={t.id} value={t.id}>{t.name}</option>
                      ))}
                    </NativeSelect>
                    {openTemplateId != null && (
                      <Link
                        href={`/templates/${openTemplateId}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={cn(
                          "inline-flex size-[2.875rem] shrink-0 items-center justify-center rounded-xl border border-border",
                          "text-muted-foreground transition-[color,background-color,border-color,scale] duration-200 ease-out",
                          "hover:bg-muted hover:text-secondary-foreground active:scale-[0.96]",
                          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30",
                        )}
                        aria-label="Open template in new tab"
                        title="Open template"
                      >
                        <ExternalLink size={16} aria-hidden />
                      </Link>
                    )}
                  </div>
                </Field>

                {templateId && (
                  <Toggle
                    label={`Permanently bind to recording${mode === "bulk" ? "s" : ""}`}
                    hint="Otherwise the template applies to this run only."
                    checked={bindTemplate}
                    onChange={setBindTemplate}
                  />
                )}
              </div>
            )}
          </div>
          )}

          {/* ── Processing ──────────────────────────────────────────────── */}
          <OverrideSection
            title="Processing"
            switchLabel="Override processing settings"
            enabled={processingEnabled}
            onEnabledChange={setProcessingEnabled}
            open={processingOpen}
            onOpenChange={setProcessingOpen}
            enabledHint={overrideEnabledHint}
          >
            <SegmentedField
              label="Transcription language"
              options={languages}
              value={language}
              onChange={setLanguage}
            />
            <SegmentedField
              label="Topic granularity"
              options={granularities}
              value={granularity}
              onChange={setGranularity}
            />

            <div className="space-y-0.5">
              <Toggle
                label="Transcription (ASR)"
                checked={enableTranscription}
                onChange={setEnableTranscription}
              />
              <Toggle
                label="Topic extraction (DeepSeek)"
                checked={enableTopics}
                onChange={setEnableTopics}
              />
              <Toggle
                label="Generate subtitles (SRT/VTT)"
                checked={enableSubtitles}
                onChange={setEnableSubtitles}
              />
              <Toggle
                label="Allow transcription errors"
                hint="Continue if ASR returns partial errors"
                checked={allowErrors}
                onChange={setAllowErrors}
              />
            </div>

            <Field label="Questions count" hint="Self-check questions (1–10)">
              <NumberInput
                integer
                min={1}
                max={10}
                value={questionsCount}
                onCommit={setQuestionsCount}
                className="w-32"
              />
            </Field>

            <Field label="Vocabulary" hint="Key terms that improve recognition accuracy">
              <TagInput tags={vocabulary} onChange={setVocabulary} placeholder="Add term…" />
            </Field>
          </OverrideSection>

          <div className="rounded-xl border border-border bg-background px-4 py-4">
            <Field
              label="LEAP playlists"
              hint="Add to these courses on this run (membership, not an upload). Upload still follows the template unless you override Upload a copy. Share links stay on the recording page."
            >
              <PlaylistPicker
                mode="form"
                selectedIds={selectedPlaylistIds}
                onChange={setSelectedPlaylistIds}
              />
            </Field>
          </div>

          {/* ── Upload ─────────────────────────────────────────────────── */}
          <OverrideSection
            title="Upload a copy"
            switchLabel="Override upload settings"
            enabled={outputEnabled}
            onEnabledChange={setOutputEnabled}
            open={outputOpen}
            onOpenChange={setOutputOpen}
            enabledHint={overrideEnabledHint}
          >
            <div className="space-y-0.5">
              <Toggle
                label="Auto-upload after processing"
                checked={autoUpload}
                onChange={setAutoUpload}
              />
              <Toggle
                label="Upload captions / subtitles"
                checked={uploadCaptions}
                onChange={setUploadCaptions}
              />
            </div>

            {Object.keys(presetsByPlatform).length > 0 ? (
              <fieldset className="space-y-3">
                <legend className={cn(FILTER_LABEL, "mb-1.5")}>
                  Presets (platforms to publish to)
                  {selectedPresetIds.length > 0 && (
                    <span className="ms-1 text-primary">· {selectedPresetIds.length} selected</span>
                  )}
                </legend>
                {Object.entries(presetsByPlatform).map(([platform, presets]) => (
                  <div key={platform}>
                    <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                      {platform}
                    </p>
                    <div className="space-y-0.5">
                      {presets.map((p) => (
                        <Toggle
                          key={p.id}
                          label={p.name}
                          checked={selectedPresetIds.includes(p.id)}
                          onChange={() => togglePreset(p.id)}
                        />
                      ))}
                    </div>
                  </div>
                ))}
              </fieldset>
            ) : (
              <p className="text-xs text-muted-foreground">
                No presets configured. Add presets to enable platform selection.
              </p>
            )}
          </OverrideSection>

          {/* ── Metadata & Platform overrides ───────────────────────────── */}
          <OverrideSection
            title="Metadata & platform overrides"
            switchLabel="Override metadata and platform settings"
            enabled={metadataEnabled}
            onEnabledChange={setMetadataEnabled}
            open={metadataOpen}
            onOpenChange={setMetadataOpen}
            enabledHint={overrideEnabledHint}
          >
            <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Global</p>
            <TemplateField
              label="Title template"
              value={titleTemplate}
              onChange={setTitleTemplate}
              placeholder="{{ display_name }}"
            />
            <TemplateField
              label="Description template"
              value={descriptionTemplate}
              onChange={setDescriptionTemplate}
              multiline
              placeholder={"{{ summary }}\n\n{{ topics }}"}
            />
            {!isSave && (
            <ThumbnailPicker
              label="Thumbnail (all platforms)"
              value={globalThumbnail}
              onChange={setGlobalThumbnail}
            />
            )}
            <DisplayConfigFields
              label="Topics in description"
              hint="How {{ topics }} renders in title/description templates"
              kind="topics"
              value={topicsDisplay}
              onChange={(patch) => setTopicsDisplay((f) => ({ ...f, ...patch }))}
            />
            <DisplayConfigFields
              label="Questions in description"
              hint="How {{ questions }} renders in title/description templates"
              kind="questions"
              value={questionsDisplay}
              onChange={(patch) => setQuestionsDisplay((f) => ({ ...f, ...patch }))}
            />

            <div className="space-y-2">
              <ActionButton
                variant="secondary"
                onClick={handleMetadataPreview}
                isPending={metadataPreviewLoading}
                icon={<Eye />}
                pendingLabel="Rendering…"
              >
                Preview render
              </ActionButton>
              {metadataPreview ? <MetadataPreviewResultBox preview={metadataPreview} /> : null}
            </div>

            <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              Platform overrides
            </p>
            <div className="space-y-2">
              <PlatformSection label="YouTube">
                <YouTubeFields
                  value={ytFields}
                  onChange={(patch) => setYtFields((f) => ({ ...f, ...patch }))}
                  showThumbnail
                  showMadeForKids
                />
              </PlatformSection>

              <PlatformSection label="VK">
                <VkFields
                  value={vkFields}
                  onChange={(patch) => setVkFields((f) => ({ ...f, ...patch }))}
                  showThumbnail
                  showPrivacyComment
                  showWallpost
                />
              </PlatformSection>

              <PlatformSection label="Yandex Disk">
                <YandexDiskFields
                  value={ydFields}
                  onChange={(patch) => setYdFields((f) => ({ ...f, ...patch }))}
                  credentialId={yandexBrowseCredentialId}
                />
              </PlatformSection>
            </div>
          </OverrideSection>

          </>}
        </div>

        {/* Footer. The error sits above the actions and wraps — truncating it to
            one line put the only copy of a real API message in a title attr. */}
        <div className="shrink-0 border-t border-border px-6 py-4">
          {runError && (
            <p role="alert" className="mb-3 rounded-xl bg-danger-fg/10 px-3 py-2 text-xs text-danger-fg">
              {runError}
            </p>
          )}
          <div className="flex items-center justify-end gap-3">
            <ActionButton variant="secondary" onClick={onClose}>
              Cancel
            </ActionButton>
            <ActionButton
              onClick={() => runMutation.mutate()}
              isPending={runMutation.isPending}
              isSuccess={runMutation.isSuccess}
              icon={isSave ? <Save /> : <Play />}
              pendingLabel={isSave ? "Saving…" : "Running…"}
            >
              {isSave ? "Save" : "Run"}
            </ActionButton>
          </div>
        </div>
      </>
    </Modal>
  );
}
