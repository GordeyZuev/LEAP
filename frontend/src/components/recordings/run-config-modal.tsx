"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, Loader2, Play, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/api/client";
import {
  FILTER_CONTROL,
  FILTER_LABEL,
  FILTER_SEGMENT_ACTIVE,
  FILTER_SEGMENT_BTN,
  FILTER_SEGMENT_IDLE,
  FILTER_SEGMENT_WRAP,
  FILTER_SELECT,
} from "@/lib/filter-field-classes";
import {
  TemplateField,
  YouTubeFields,
  VkFields,
  YandexDiskFields,
  DEFAULT_YOUTUBE_FIELDS,
  DEFAULT_VK_FIELDS,
  DEFAULT_YANDEX_DISK_FIELDS,
  type YouTubeFieldsValue,
  type VkFieldsValue,
  type YandexDiskFieldsValue,
} from "@/components/platforms/platform-fields";
import { ThumbnailPicker } from "@/components/platforms/thumbnail-picker";
import { TagInput } from "@/components/ui/tag-input";
import { useGranularities, useLanguages } from "@/hooks/use-references";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface TemplateItem { id: number; name: string }
interface TemplateListResponse { items: TemplateItem[]; total: number }
interface PresetItem { id: number; name: string; platform: string }
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
      prompt?: string;
      allow_errors?: boolean;
      questions_count?: number;
      vocabulary?: string[];
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
  onSuccess?: () => void;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// SectionToggle
// ---------------------------------------------------------------------------

function SectionToggle({ enabled, onToggle }: { enabled: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={enabled}
      onClick={(e) => { e.stopPropagation(); onToggle(); }}
      className={cn(
        "relative h-5 w-9 shrink-0 rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#224C87]/30",
        enabled ? "bg-[#224C87]" : "bg-gray-200"
      )}
    >
      <span
        className={cn(
          "absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all duration-150",
          enabled ? "left-[1.125rem]" : "left-0.5"
        )}
      />
    </button>
  );
}

// ---------------------------------------------------------------------------
// PlatformSection — collapsible sub-accordion for per-platform metadata
// ---------------------------------------------------------------------------

function PlatformSection({ label, children }: { label: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-xl border border-[#EAEAEA] bg-[#FAFAFA]">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium text-gray-700 hover:text-gray-900"
      >
        {label}
        <ChevronDown
          size={15}
          className={cn("shrink-0 text-gray-400 transition-transform", open && "rotate-180")}
        />
      </button>
      {open && (
        <div className="space-y-3 border-t border-[#EAEAEA] px-4 pb-4 pt-3">
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
  onSuccess,
}: RunConfigModalProps) {
  const qc = useQueryClient();
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
  const [transcriptionPrompt, setTranscriptionPrompt] = useState("");
  const [allowErrors, setAllowErrors] = useState(false);
  const [questionsCount, setQuestionsCount] = useState(5);
  const [vocabulary, setVocabulary] = useState<string[]>([]);

  // ── Output ────────────────────────────────────────────────────────────────
  const [outputEnabled, setOutputEnabled] = useState(false);
  const [outputOpen, setOutputOpen] = useState(false);
  const [autoUpload, setAutoUpload] = useState(true);
  const [uploadCaptions, setUploadCaptions] = useState(true);
  const [selectedPresetIds, setSelectedPresetIds] = useState<number[]>([]);

  // ── Metadata ──────────────────────────────────────────────────────────────
  const [metadataEnabled, setMetadataEnabled] = useState(false);
  const [metadataOpen, setMetadataOpen] = useState(false);
  const [titleTemplate, setTitleTemplate] = useState("");
  const [descriptionTemplate, setDescriptionTemplate] = useState("");
  const [globalThumbnail, setGlobalThumbnail] = useState("");
  const [ytFields, setYtFields] = useState<YouTubeFieldsValue>({ ...DEFAULT_YOUTUBE_FIELDS });
  const [vkFields, setVkFields] = useState<VkFieldsValue>({ ...DEFAULT_VK_FIELDS });
  const [ydFields, setYdFields] = useState<YandexDiskFieldsValue>({ ...DEFAULT_YANDEX_DISK_FIELDS });

  // ── Reference data ────────────────────────────────────────────────────────
  const { data: templatesData } = useQuery<TemplateListResponse>({
    queryKey: ["templates-dropdown"],
    queryFn: async () => (await apiClient.get<TemplateListResponse>("/templates?per_page=100")).data,
    enabled: open,
  });

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
            ...(transcriptionPrompt ? { prompt: transcriptionPrompt } : {}),
            allow_errors: allowErrors,
            questions_count: questionsCount,
            ...(vocabulary.length > 0 ? { vocabulary } : {}),
          },
        };
      }

      if (outputEnabled) {
        const outputCfg: Record<string, unknown> = {
          auto_upload: autoUpload,
          upload_captions: uploadCaptions,
        };
        if (selectedPresetIds.length > 0) outputCfg.preset_ids = selectedPresetIds;
        body.output_config = outputCfg;
      }

      if (metadataEnabled) {
        const meta: Record<string, unknown> = {};
        if (titleTemplate) meta.title_template = titleTemplate;
        if (descriptionTemplate) meta.description_template = descriptionTemplate;

        const yt: Record<string, unknown> = {};
        if (ytFields.privacy) yt.privacy = ytFields.privacy;
        if (ytFields.playlist_id) yt.playlist_id = ytFields.playlist_id;
        const ytThumb = ytFields.thumbnail_name || globalThumbnail;
        if (ytThumb) yt.thumbnail_name = ytThumb;
        if (ytFields.title_template) yt.title_template = ytFields.title_template;
        if (ytFields.description_template) yt.description_template = ytFields.description_template;
        if (ytFields.category_id) yt.category_id = ytFields.category_id;
        if (ytFields.tags.length > 0) yt.tags = ytFields.tags;
        if (ytFields.made_for_kids) yt.made_for_kids = true;
        if (Object.keys(yt).length > 0) meta.youtube = yt;

        const vk: Record<string, unknown> = {};
        if (vkFields.group_id) vk.group_id = vkFields.group_id;
        if (vkFields.album_id) vk.album_id = vkFields.album_id;
        const vkThumb = vkFields.thumbnail_name || globalThumbnail;
        if (vkThumb) vk.thumbnail_name = vkThumb;
        if (vkFields.title_template) vk.title_template = vkFields.title_template;
        if (vkFields.description_template) vk.description_template = vkFields.description_template;
        if (vkFields.privacy_view !== "") vk.privacy_view = Number(vkFields.privacy_view);
        if (vkFields.privacy_comment !== "") vk.privacy_comment = Number(vkFields.privacy_comment);
        if (vkFields.wallpost) vk.wallpost = true;
        if (Object.keys(vk).length > 0) meta.vk = vk;

        const yd: Record<string, unknown> = {};
        if (ydFields.folder_path_template) yd.folder_path_template = ydFields.folder_path_template;
        if (ydFields.filename_template) yd.filename_template = ydFields.filename_template;
        if (ydFields.overwrite) yd.overwrite = true;
        if (ydFields.publish) yd.publish = true;
        if (Object.keys(yd).length > 0) meta.yandex_disk = yd;

        if (Object.keys(meta).length > 0) body.metadata_config = meta;
      }

      if (mode === "single") {
        return apiClient.post(`/recordings/${recordingId}/run`, body);
      }
      return apiClient.post("/recordings/bulk/run", {
        recording_ids: recordingIds,
        ...body,
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["recordings"] });
      if (recordingId) qc.invalidateQueries({ queryKey: ["recording", String(recordingId)] });
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
    setTranscriptionPrompt("");
    setAllowErrors(false);
    setQuestionsCount(5);
    setVocabulary([]);
    setOutputEnabled(false);
    setOutputOpen(false);
    setAutoUpload(true);
    setUploadCaptions(true);
    setSelectedPresetIds([]);
    setMetadataEnabled(false);
    setMetadataOpen(false);
    setTitleTemplate("");
    setDescriptionTemplate("");
    setGlobalThumbnail("");
    setYtFields({ ...DEFAULT_YOUTUBE_FIELDS });
    setVkFields({ ...DEFAULT_VK_FIELDS });
    setYdFields({ ...DEFAULT_YANDEX_DISK_FIELDS });
    /* eslint-enable react-hooks/set-state-in-effect */
    runMutation.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // ── Pre-fill from resolved config (single mode) ───────────────────────────
  useEffect(() => {
    if (!open || !existingConfig) return;
    /* eslint-disable react-hooks/set-state-in-effect */
    if (existingConfig.template_id) setTemplateId(existingConfig.template_id);

    const pc = existingConfig.processing_config;
    if (pc) {
      setProcessingEnabled(true);
      setProcessingOpen(true);
      const t = pc.transcription;
      if (t) {
        if (t.language != null) setLanguage(t.language);
        if (t.granularity != null) setGranularity(t.granularity);
        if (t.enable_transcription != null) setEnableTranscription(t.enable_transcription);
        if (t.enable_topics != null) setEnableTopics(t.enable_topics);
        if (t.enable_subtitles != null) setEnableSubtitles(t.enable_subtitles);
        if (t.prompt != null) setTranscriptionPrompt(t.prompt);
        if (t.allow_errors != null) setAllowErrors(t.allow_errors);
        if (t.questions_count != null) setQuestionsCount(t.questions_count);
        if (t.vocabulary != null) setVocabulary(t.vocabulary);
      }
    }

    const oc = existingConfig.output_config;
    if (oc) {
      setOutputEnabled(true);
      setOutputOpen(true);
      if (oc.auto_upload != null) setAutoUpload(oc.auto_upload);
      if (oc.upload_captions != null) setUploadCaptions(oc.upload_captions);
      if (oc.preset_ids) setSelectedPresetIds(oc.preset_ids);
    }

    const mc = existingConfig.metadata_config;
    if (mc) {
      setMetadataEnabled(true);
      setMetadataOpen(true);
      if (mc.title_template) setTitleTemplate(mc.title_template);
      if (mc.description_template) setDescriptionTemplate(mc.description_template);

      if (mc.youtube) {
        const yt = mc.youtube;
        setYtFields({
          title_template: yt.title_template ?? "",
          description_template: yt.description_template ?? "",
          privacy: yt.privacy ?? "",
          category_id: yt.category_id != null ? String(yt.category_id) : "",
          playlist_id: yt.playlist_id ?? "",
          thumbnail_name: yt.thumbnail_name ?? "",
          tags: yt.tags ?? [],
          made_for_kids: yt.made_for_kids ?? false,
        });
      }

      if (mc.vk) {
        const vk = mc.vk;
        setVkFields({
          title_template: vk.title_template ?? "",
          description_template: vk.description_template ?? "",
          privacy_view: vk.privacy_view != null ? String(vk.privacy_view) : "",
          privacy_comment: vk.privacy_comment != null ? String(vk.privacy_comment) : "",
          group_id: vk.group_id != null ? String(vk.group_id) : "",
          album_id: vk.album_id != null ? String(vk.album_id) : "",
          thumbnail_name: vk.thumbnail_name ?? "",
          wallpost: vk.wallpost ?? false,
        });
      }

      if (mc.yandex_disk) {
        const yd = mc.yandex_disk;
        setYdFields({
          folder_path_template: yd.folder_path_template ?? "",
          filename_template: yd.filename_template ?? "",
          overwrite: yd.overwrite ?? false,
          publish: yd.publish ?? false,
        });
      }
    }
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [open, existingConfig]);

  // ── ESC to close ──────────────────────────────────────────────────────────
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const count = mode === "bulk" ? (recordingIds?.length ?? 0) : 1;
  const title =
    mode === "single"
      ? `Run with config${recordingName ? `: "${recordingName}"` : recordingId ? ` #${recordingId}` : ""}`
      : `Bulk run ${count} recording${count !== 1 ? "s" : ""} with config`;

  const runError =
    (runMutation.error as { response?: { data?: { detail?: string } } } | null)?.response?.data?.detail ??
    (runMutation.isError ? "Failed to run" : null);

  function togglePreset(id: number) {
    setSelectedPresetIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }

  const presetsByPlatform = (presetsData?.items ?? []).reduce<Record<string, PresetItem[]>>(
    (acc, p) => { (acc[p.platform] = acc[p.platform] ?? []).push(p); return acc; },
    {}
  );

  function handleProcessingToggle() {
    const next = !processingEnabled;
    setProcessingEnabled(next);
    if (next && !processingOpen) setProcessingOpen(true);
  }

  function handleOutputToggle() {
    const next = !outputEnabled;
    setOutputEnabled(next);
    if (next && !outputOpen) setOutputOpen(true);
  }

  function handleMetadataToggle() {
    const next = !metadataEnabled;
    setMetadataEnabled(next);
    if (next && !metadataOpen) setMetadataOpen(true);
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="flex max-h-[92vh] w-full max-w-2xl flex-col rounded-2xl bg-white shadow-xl mx-4">
        {/* Header */}
        <div className="flex shrink-0 items-center justify-between border-b border-[#EAEAEA] px-6 py-4">
          <h2 className="min-w-0 truncate text-sm font-semibold text-gray-900">{title}</h2>
          <button
            onClick={onClose}
            className="ml-4 shrink-0 text-gray-400 hover:text-gray-600 transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto divide-y divide-[#F0F0F0]">
          {configLoading ? (
            <div className="flex items-center justify-center gap-2 py-14 text-sm text-gray-400">
              <Loader2 size={16} className="animate-spin text-[#224C87]" />
              Загрузка конфига…
            </div>
          ) : <>

          {/* ── Template ────────────────────────────────────────────────── */}
          <div className="px-6 py-4">
            <button
              type="button"
              onClick={() => setTemplateOpen((v) => !v)}
              className="flex w-full items-center gap-2 text-left"
            >
              <span className="flex-1 text-sm font-semibold text-gray-800">Template</span>
              {templateId && <span className="text-xs font-medium text-[#224C87]">selected</span>}
              <ChevronDown
                size={16}
                className={cn("shrink-0 text-gray-400 transition-transform", templateOpen && "rotate-180")}
              />
            </button>

            {templateOpen && (
              <div className="mt-4 space-y-4">
                <div className="space-y-1.5">
                  <span className={FILTER_LABEL}>Template to use for this run</span>
                  <select
                    value={templateId ?? ""}
                    onChange={(e) => setTemplateId(e.target.value ? Number(e.target.value) : null)}
                    className={FILTER_SELECT}
                  >
                    <option value="">Use recording&apos;s assigned template</option>
                    {(templatesData?.items ?? []).map((t) => (
                      <option key={t.id} value={t.id}>{t.name}</option>
                    ))}
                  </select>
                </div>

                {templateId && (
                  <label className="flex cursor-pointer items-center gap-2.5">
                    <input
                      type="checkbox"
                      checked={bindTemplate}
                      onChange={(e) => setBindTemplate(e.target.checked)}
                      className="accent-[#224C87]"
                    />
                    <span className="text-sm text-gray-700">
                      Permanently bind to recording{mode === "bulk" ? "s" : ""}
                    </span>
                  </label>
                )}

                {!templateId && (
                  <p className="text-xs text-gray-400">
                    Leave empty to use the recording&apos;s current template (or system defaults).
                  </p>
                )}
              </div>
            )}
          </div>

          {/* ── Processing ──────────────────────────────────────────────── */}
          <div className="px-6 py-4">
            <div className="flex items-center gap-3">
              <SectionToggle enabled={processingEnabled} onToggle={handleProcessingToggle} />
              <button
                type="button"
                onClick={() => setProcessingOpen((v) => !v)}
                className="flex flex-1 items-center gap-2 text-left"
              >
                <span className="text-sm font-semibold text-gray-800">Processing</span>
                {!processingEnabled && (
                  <span className="text-xs text-gray-400">using template defaults</span>
                )}
                <ChevronDown
                  size={16}
                  className={cn("ml-auto shrink-0 text-gray-400 transition-transform", processingOpen && "rotate-180")}
                />
              </button>
            </div>

            {processingOpen && (
              <div className={cn("mt-4 space-y-4", !processingEnabled && "pointer-events-none opacity-50")}>
                <div className="space-y-1.5">
                  <span className={FILTER_LABEL}>Transcription language</span>
                  <div className={FILTER_SEGMENT_WRAP}>
                    {languages.map(({ value, label }) => (
                      <button
                        key={value}
                        type="button"
                        className={cn(FILTER_SEGMENT_BTN, language === value ? FILTER_SEGMENT_ACTIVE : FILTER_SEGMENT_IDLE)}
                        onClick={() => setLanguage(value)}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="space-y-1.5">
                  <span className={FILTER_LABEL}>Topic granularity</span>
                  <div className={FILTER_SEGMENT_WRAP}>
                    {granularities.map(({ value, label }) => (
                      <button
                        key={value}
                        type="button"
                        className={cn(FILTER_SEGMENT_BTN, granularity === value ? FILTER_SEGMENT_ACTIVE : FILTER_SEGMENT_IDLE)}
                        onClick={() => setGranularity(value)}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="space-y-2.5">
                  {[
                    { key: "transcription", label: "Transcription (ASR)",            val: enableTranscription, set: setEnableTranscription },
                    { key: "topics",        label: "Topic extraction (DeepSeek)",     val: enableTopics,        set: setEnableTopics },
                    { key: "subtitles",     label: "Generate subtitles (SRT/VTT)",    val: enableSubtitles,     set: setEnableSubtitles },
                  ].map(({ key, label, val, set }) => (
                    <label key={key} className="flex cursor-pointer items-center gap-2.5">
                      <input
                        type="checkbox"
                        checked={val}
                        onChange={(e) => set(e.target.checked)}
                        className="accent-[#224C87]"
                      />
                      <span className="text-sm text-gray-700">{label}</span>
                    </label>
                  ))}
                </div>

                <TemplateField
                  label="Transcription prompt"
                  value={transcriptionPrompt}
                  onChange={setTranscriptionPrompt}
                  multiline
                  placeholder="University lecture: machine learning, neural networks…"
                />

                <label className="flex cursor-pointer items-center gap-2.5">
                  <input
                    type="checkbox"
                    checked={allowErrors}
                    onChange={(e) => setAllowErrors(e.target.checked)}
                    className="accent-[#224C87]"
                  />
                  <span className="text-sm text-gray-700">Allow transcription errors</span>
                </label>

                <div className="space-y-1.5">
                  <span className={FILTER_LABEL}>Questions count</span>
                  <input
                    type="number"
                    min={0}
                    max={20}
                    value={questionsCount}
                    onChange={(e) => setQuestionsCount(parseInt(e.target.value, 10) || 0)}
                    className={cn(FILTER_CONTROL, "w-32")}
                  />
                </div>

                <div className="space-y-1.5">
                  <span className={FILTER_LABEL}>Vocabulary</span>
                  <TagInput
                    tags={vocabulary}
                    onChange={setVocabulary}
                    placeholder="Add term…"
                  />
                </div>
              </div>
            )}
          </div>

          {/* ── Output ──────────────────────────────────────────────────── */}
          <div className="px-6 py-4">
            <div className="flex items-center gap-3">
              <SectionToggle enabled={outputEnabled} onToggle={handleOutputToggle} />
              <button
                type="button"
                onClick={() => setOutputOpen((v) => !v)}
                className="flex flex-1 items-center gap-2 text-left"
              >
                <span className="text-sm font-semibold text-gray-800">Output &amp; Upload</span>
                {!outputEnabled && (
                  <span className="text-xs text-gray-400">using template defaults</span>
                )}
                <ChevronDown
                  size={16}
                  className={cn("ml-auto shrink-0 text-gray-400 transition-transform", outputOpen && "rotate-180")}
                />
              </button>
            </div>

            {outputOpen && (
              <div className={cn("mt-4 space-y-4", !outputEnabled && "pointer-events-none opacity-50")}>
                <label className="flex cursor-pointer items-center gap-2.5">
                  <input type="checkbox" checked={autoUpload} onChange={(e) => setAutoUpload(e.target.checked)} className="accent-[#224C87]" />
                  <span className="text-sm text-gray-700">Auto-upload after processing</span>
                </label>
                <label className="flex cursor-pointer items-center gap-2.5">
                  <input type="checkbox" checked={uploadCaptions} onChange={(e) => setUploadCaptions(e.target.checked)} className="accent-[#224C87]" />
                  <span className="text-sm text-gray-700">Upload captions / subtitles</span>
                </label>

                {Object.keys(presetsByPlatform).length > 0 && (
                  <div className="space-y-3">
                    <span className={FILTER_LABEL}>
                      Presets (platforms to publish to)
                      {selectedPresetIds.length > 0 && (
                        <span className="ml-1 text-[#224C87]">· {selectedPresetIds.length} selected</span>
                      )}
                    </span>
                    {Object.entries(presetsByPlatform).map(([platform, presets]) => (
                      <div key={platform}>
                        <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-gray-400">{platform}</p>
                        <div className="space-y-1.5">
                          {presets.map((p) => (
                            <label key={p.id} className="flex cursor-pointer items-center gap-2.5">
                              <input
                                type="checkbox"
                                checked={selectedPresetIds.includes(p.id)}
                                onChange={() => togglePreset(p.id)}
                                className="accent-[#224C87]"
                              />
                              <span className="text-sm text-gray-700">{p.name}</span>
                            </label>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {Object.keys(presetsByPlatform).length === 0 && (
                  <p className="text-xs text-gray-400">No presets configured. Add presets to enable platform selection.</p>
                )}
              </div>
            )}
          </div>

          {/* ── Metadata & Platform overrides ───────────────────────────── */}
          <div className="px-6 py-4">
            <div className="flex items-center gap-3">
              <SectionToggle enabled={metadataEnabled} onToggle={handleMetadataToggle} />
              <button
                type="button"
                onClick={() => setMetadataOpen((v) => !v)}
                className="flex flex-1 items-center gap-2 text-left"
              >
                <span className="text-sm font-semibold text-gray-800">Metadata &amp; Platform overrides</span>
                {!metadataEnabled && (
                  <span className="text-xs text-gray-400">using template defaults</span>
                )}
                <ChevronDown
                  size={16}
                  className={cn("ml-auto shrink-0 text-gray-400 transition-transform", metadataOpen && "rotate-180")}
                />
              </button>
            </div>

            {metadataOpen && (
              <div className={cn("mt-4 space-y-5", !metadataEnabled && "pointer-events-none opacity-50")}>
                {/* Global templates */}
                <div className="space-y-4">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">Global</p>
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
                  <ThumbnailPicker
                    label="Thumbnail (all platforms)"
                    value={globalThumbnail}
                    onChange={setGlobalThumbnail}
                    placeholder="Platform-specific thumbnails override this"
                  />
                </div>

                {/* Platform subsections */}
                <div className="space-y-2">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">Platform overrides</p>

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
                    />
                  </PlatformSection>
                </div>
              </div>
            )}
          </div>

          </>}
        </div>

        {/* Footer */}
        <div className="flex shrink-0 items-center justify-end gap-3 border-t border-[#EAEAEA] px-6 py-4">
          {runError && (
            <p className="flex-1 truncate text-xs text-red-500" title={runError}>{runError}</p>
          )}
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl border border-[#D9D9D9] px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => runMutation.mutate()}
            disabled={runMutation.isPending}
            className="flex items-center gap-1.5 rounded-xl bg-[#224C87] px-4 py-2 text-sm font-medium text-white hover:bg-[#1a3d6e] disabled:opacity-50 transition-colors"
          >
            {runMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
            Run
          </button>
        </div>
      </div>
    </div>
  );
}
