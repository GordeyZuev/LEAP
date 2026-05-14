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
} from "@/lib/filter-field-classes";

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

const LANGUAGES = [
  { value: "ru", label: "Русский" },
  { value: "en", label: "English" },
  { value: "auto", label: "Auto" },
];

const GRANULARITIES = [
  { value: "short", label: "Short" },
  { value: "medium", label: "Medium" },
  { value: "long", label: "Long" },
];

const YT_PRIVACY_OPTIONS = [
  { value: "", label: "— default —" },
  { value: "public", label: "Public" },
  { value: "unlisted", label: "Unlisted" },
  { value: "private", label: "Private" },
];

const VK_PRIVACY_OPTIONS = [
  { value: "", label: "— default —" },
  { value: "0", label: "All users" },
  { value: "1", label: "Friends" },
  { value: "2", label: "Friends of friends" },
  { value: "3", label: "Only me" },
];

// ---------------------------------------------------------------------------
// SectionToggle — the on/off switch shared by override sections
// ---------------------------------------------------------------------------

function SectionToggle({
  enabled,
  onToggle,
}: {
  enabled: boolean;
  onToggle: () => void;
}) {
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
          "absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform",
          enabled ? "translate-x-4" : "translate-x-0.5"
        )}
      />
    </button>
  );
}

// ---------------------------------------------------------------------------
// Sub-accordion for per-platform metadata
// ---------------------------------------------------------------------------

function PlatformSection({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
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
        <div className="border-t border-[#EAEAEA] px-4 pb-4 pt-3 space-y-3">
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

  // YouTube
  const [ytPrivacy, setYtPrivacy] = useState("");
  const [ytPlaylistId, setYtPlaylistId] = useState("");
  const [ytThumbnailName, setYtThumbnailName] = useState("");
  const [ytTitleTemplate, setYtTitleTemplate] = useState("");
  const [ytDescriptionTemplate, setYtDescriptionTemplate] = useState("");
  const [ytCategoryId, setYtCategoryId] = useState("");
  const [ytTags, setYtTags] = useState("");

  // VK
  const [vkAlbumId, setVkAlbumId] = useState("");
  const [vkGroupId, setVkGroupId] = useState("");
  const [vkThumbnailName, setVkThumbnailName] = useState("");
  const [vkTitleTemplate, setVkTitleTemplate] = useState("");
  const [vkDescriptionTemplate, setVkDescriptionTemplate] = useState("");
  const [vkPrivacyView, setVkPrivacyView] = useState("");
  const [vkPrivacyComment, setVkPrivacyComment] = useState("");
  const [vkWallpost, setVkWallpost] = useState(false);

  // Yandex Disk
  const [ydFolderPathTemplate, setYdFolderPathTemplate] = useState("");
  const [ydFilenameTemplate, setYdFilenameTemplate] = useState("");
  const [ydOverwrite, setYdOverwrite] = useState(false);
  const [ydPublish, setYdPublish] = useState(false);

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
        if (ytPrivacy) yt.privacy = ytPrivacy;
        if (ytPlaylistId) yt.playlist_id = ytPlaylistId;
        if (ytThumbnailName) yt.thumbnail_name = ytThumbnailName;
        if (ytTitleTemplate) yt.title_template = ytTitleTemplate;
        if (ytDescriptionTemplate) yt.description_template = ytDescriptionTemplate;
        if (ytCategoryId) yt.category_id = ytCategoryId;
        if (ytTags) yt.tags = ytTags.split(",").map((t) => t.trim()).filter(Boolean);
        if (Object.keys(yt).length > 0) meta.youtube = yt;

        const vk: Record<string, unknown> = {};
        if (vkAlbumId) vk.album_id = vkAlbumId;
        if (vkGroupId) vk.group_id = Number(vkGroupId);
        if (vkThumbnailName) vk.thumbnail_name = vkThumbnailName;
        if (vkTitleTemplate) vk.title_template = vkTitleTemplate;
        if (vkDescriptionTemplate) vk.description_template = vkDescriptionTemplate;
        if (vkPrivacyView !== "") vk.privacy_view = Number(vkPrivacyView);
        if (vkPrivacyComment !== "") vk.privacy_comment = Number(vkPrivacyComment);
        if (vkWallpost) vk.wallpost = true;
        if (Object.keys(vk).length > 0) meta.vk = vk;

        const yd: Record<string, unknown> = {};
        if (ydFolderPathTemplate) yd.folder_path_template = ydFolderPathTemplate;
        if (ydFilenameTemplate) yd.filename_template = ydFilenameTemplate;
        if (ydOverwrite) yd.overwrite = true;
        if (ydPublish) yd.publish = true;
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

  // ── Reset on open ─────────────────────────────────────────────────────────
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
    setOutputEnabled(false);
    setOutputOpen(false);
    setAutoUpload(true);
    setUploadCaptions(true);
    setSelectedPresetIds([]);
    setMetadataEnabled(false);
    setMetadataOpen(false);
    setTitleTemplate("");
    setDescriptionTemplate("");
    setYtPrivacy("");
    setYtPlaylistId("");
    setYtThumbnailName("");
    setYtTitleTemplate("");
    setYtDescriptionTemplate("");
    setYtCategoryId("");
    setYtTags("");
    setVkAlbumId("");
    setVkGroupId("");
    setVkThumbnailName("");
    setVkTitleTemplate("");
    setVkDescriptionTemplate("");
    setVkPrivacyView("");
    setVkPrivacyComment("");
    setVkWallpost(false);
    setYdFolderPathTemplate("");
    setYdFilenameTemplate("");
    setYdOverwrite(false);
    setYdPublish(false);
    /* eslint-enable react-hooks/set-state-in-effect */
    runMutation.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Pre-fill from resolved config (single mode only); runs after reset effect
  useEffect(() => {
    if (!open || !existingConfig) return;
    /* eslint-disable react-hooks/set-state-in-effect */
    if (existingConfig.template_id) {
      setTemplateId(existingConfig.template_id);
    }

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

      const yt = mc.youtube;
      if (yt) {
        if (yt.privacy) setYtPrivacy(yt.privacy);
        if (yt.playlist_id) setYtPlaylistId(yt.playlist_id);
        if (yt.thumbnail_name) setYtThumbnailName(yt.thumbnail_name);
        if (yt.title_template) setYtTitleTemplate(yt.title_template);
        if (yt.description_template) setYtDescriptionTemplate(yt.description_template);
        if (yt.category_id != null) setYtCategoryId(String(yt.category_id));
        if (yt.tags) setYtTags(yt.tags.join(", "));
      }

      const vk = mc.vk;
      if (vk) {
        if (vk.album_id != null) setVkAlbumId(String(vk.album_id));
        if (vk.group_id != null) setVkGroupId(String(vk.group_id));
        if (vk.thumbnail_name) setVkThumbnailName(vk.thumbnail_name);
        if (vk.title_template) setVkTitleTemplate(vk.title_template);
        if (vk.description_template) setVkDescriptionTemplate(vk.description_template);
        if (vk.privacy_view != null) setVkPrivacyView(String(vk.privacy_view));
        if (vk.privacy_comment != null) setVkPrivacyComment(String(vk.privacy_comment));
        if (vk.wallpost) setVkWallpost(vk.wallpost);
      }

      const yd = mc.yandex_disk;
      if (yd) {
        if (yd.folder_path_template) setYdFolderPathTemplate(yd.folder_path_template);
        if (yd.filename_template) setYdFilenameTemplate(yd.filename_template);
        if (yd.overwrite) setYdOverwrite(yd.overwrite);
        if (yd.publish) setYdPublish(yd.publish);
      }
    }
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [open, existingConfig]);

  // ESC to close
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

          {/* ── Template section ────────────────────────────────────────── */}
          <div className="px-6 py-4">
            <button
              type="button"
              onClick={() => setTemplateOpen((v) => !v)}
              className="flex w-full items-center gap-2 text-left"
            >
              <span className="flex-1 text-sm font-semibold text-gray-800">Template</span>
              {templateId && (
                <span className="text-xs text-[#224C87] font-medium">selected</span>
              )}
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
                    className={FILTER_CONTROL}
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

          {/* ── Processing section ──────────────────────────────────────── */}
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
                    {LANGUAGES.map(({ value, label }) => (
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
                    {GRANULARITIES.map(({ value, label }) => (
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
                    { key: "transcription", label: "Transcription (ASR)", val: enableTranscription, set: setEnableTranscription },
                    { key: "topics", label: "Topic extraction (DeepSeek)", val: enableTopics, set: setEnableTopics },
                    { key: "subtitles", label: "Generate subtitles (SRT/VTT)", val: enableSubtitles, set: setEnableSubtitles },
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
              </div>
            )}
          </div>

          {/* ── Output section ──────────────────────────────────────────── */}
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
                  <input
                    type="checkbox"
                    checked={autoUpload}
                    onChange={(e) => setAutoUpload(e.target.checked)}
                    className="accent-[#224C87]"
                  />
                  <span className="text-sm text-gray-700">Auto-upload after processing</span>
                </label>

                <label className="flex cursor-pointer items-center gap-2.5">
                  <input
                    type="checkbox"
                    checked={uploadCaptions}
                    onChange={(e) => setUploadCaptions(e.target.checked)}
                    className="accent-[#224C87]"
                  />
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
                        <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-gray-400">
                          {platform}
                        </p>
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

          {/* ── Metadata section ────────────────────────────────────────── */}
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
                  <div className="space-y-1.5">
                    <span className={FILTER_LABEL}>Title template</span>
                    <input
                      type="text"
                      value={titleTemplate}
                      onChange={(e) => setTitleTemplate(e.target.value)}
                      placeholder="{{ display_name }}"
                      className={FILTER_CONTROL}
                    />
                    <p className="text-[11px] text-gray-400">
                      Overrides the title for all platforms. Jinja2 — use <code className="font-mono">{"{{ display_name }}"}</code>, <code className="font-mono">{"{{ themes }}"}</code>, etc.
                    </p>
                  </div>
                  <div className="space-y-1.5">
                    <span className={FILTER_LABEL}>Description template</span>
                    <textarea
                      value={descriptionTemplate}
                      onChange={(e) => setDescriptionTemplate(e.target.value)}
                      rows={3}
                      placeholder={"{{ summary }}\n\n{{ topics }}"}
                      className={cn(FILTER_CONTROL, "resize-y")}
                    />
                  </div>
                </div>

                {/* Platform subsections */}
                <div className="space-y-2">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">Platform overrides</p>

                  {/* YouTube */}
                  <PlatformSection label="YouTube">
                    <div className="grid grid-cols-2 gap-3">
                      <div className="space-y-1.5">
                        <span className={FILTER_LABEL}>Privacy</span>
                        <select value={ytPrivacy} onChange={(e) => setYtPrivacy(e.target.value)} className={FILTER_CONTROL}>
                          {YT_PRIVACY_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                        </select>
                      </div>
                      <div className="space-y-1.5">
                        <span className={FILTER_LABEL}>Category ID</span>
                        <input
                          type="text"
                          value={ytCategoryId}
                          onChange={(e) => setYtCategoryId(e.target.value)}
                          placeholder="27"
                          className={FILTER_CONTROL}
                        />
                      </div>
                    </div>
                    <div className="space-y-1.5">
                      <span className={FILTER_LABEL}>Playlist ID</span>
                      <input
                        type="text"
                        value={ytPlaylistId}
                        onChange={(e) => setYtPlaylistId(e.target.value)}
                        placeholder="PLxxxxxxxxxxxxxxxx"
                        className={FILTER_CONTROL}
                      />
                    </div>
                    <div className="space-y-1.5">
                      <span className={FILTER_LABEL}>Thumbnail filename</span>
                      <input
                        type="text"
                        value={ytThumbnailName}
                        onChange={(e) => setYtThumbnailName(e.target.value)}
                        placeholder="python_base.png"
                        className={FILTER_CONTROL}
                      />
                    </div>
                    <div className="space-y-1.5">
                      <span className={FILTER_LABEL}>Tags (comma-separated)</span>
                      <input
                        type="text"
                        value={ytTags}
                        onChange={(e) => setYtTags(e.target.value)}
                        placeholder="AI, ML, lecture"
                        className={FILTER_CONTROL}
                      />
                    </div>
                    <div className="space-y-1.5">
                      <span className={FILTER_LABEL}>Title template (YouTube-specific)</span>
                      <input
                        type="text"
                        value={ytTitleTemplate}
                        onChange={(e) => setYtTitleTemplate(e.target.value)}
                        placeholder="overrides global title for YouTube"
                        className={FILTER_CONTROL}
                      />
                    </div>
                    <div className="space-y-1.5">
                      <span className={FILTER_LABEL}>Description template (YouTube-specific)</span>
                      <textarea
                        value={ytDescriptionTemplate}
                        onChange={(e) => setYtDescriptionTemplate(e.target.value)}
                        rows={3}
                        placeholder="overrides global description for YouTube"
                        className={cn(FILTER_CONTROL, "resize-y")}
                      />
                    </div>
                  </PlatformSection>

                  {/* VK */}
                  <PlatformSection label="VK">
                    <div className="grid grid-cols-2 gap-3">
                      <div className="space-y-1.5">
                        <span className={FILTER_LABEL}>Album ID</span>
                        <input
                          type="text"
                          value={vkAlbumId}
                          onChange={(e) => setVkAlbumId(e.target.value)}
                          placeholder="123456"
                          className={FILTER_CONTROL}
                        />
                      </div>
                      <div className="space-y-1.5">
                        <span className={FILTER_LABEL}>Group ID</span>
                        <input
                          type="text"
                          value={vkGroupId}
                          onChange={(e) => setVkGroupId(e.target.value)}
                          placeholder="123456"
                          className={FILTER_CONTROL}
                        />
                      </div>
                    </div>
                    <div className="space-y-1.5">
                      <span className={FILTER_LABEL}>Thumbnail filename</span>
                      <input
                        type="text"
                        value={vkThumbnailName}
                        onChange={(e) => setVkThumbnailName(e.target.value)}
                        placeholder="hse_ai.jpg"
                        className={FILTER_CONTROL}
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div className="space-y-1.5">
                        <span className={FILTER_LABEL}>Privacy — view</span>
                        <select value={vkPrivacyView} onChange={(e) => setVkPrivacyView(e.target.value)} className={FILTER_CONTROL}>
                          {VK_PRIVACY_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                        </select>
                      </div>
                      <div className="space-y-1.5">
                        <span className={FILTER_LABEL}>Privacy — comments</span>
                        <select value={vkPrivacyComment} onChange={(e) => setVkPrivacyComment(e.target.value)} className={FILTER_CONTROL}>
                          {VK_PRIVACY_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                        </select>
                      </div>
                    </div>
                    <label className="flex cursor-pointer items-center gap-2.5">
                      <input
                        type="checkbox"
                        checked={vkWallpost}
                        onChange={(e) => setVkWallpost(e.target.checked)}
                        className="accent-[#224C87]"
                      />
                      <span className="text-sm text-gray-700">Post to wall</span>
                    </label>
                    <div className="space-y-1.5">
                      <span className={FILTER_LABEL}>Title template (VK-specific)</span>
                      <input
                        type="text"
                        value={vkTitleTemplate}
                        onChange={(e) => setVkTitleTemplate(e.target.value)}
                        placeholder="overrides global title for VK"
                        className={FILTER_CONTROL}
                      />
                    </div>
                    <div className="space-y-1.5">
                      <span className={FILTER_LABEL}>Description template (VK-specific)</span>
                      <textarea
                        value={vkDescriptionTemplate}
                        onChange={(e) => setVkDescriptionTemplate(e.target.value)}
                        rows={3}
                        placeholder="overrides global description for VK"
                        className={cn(FILTER_CONTROL, "resize-y")}
                      />
                    </div>
                  </PlatformSection>

                  {/* Yandex Disk */}
                  <PlatformSection label="Yandex Disk">
                    <div className="space-y-1.5">
                      <span className={FILTER_LABEL}>Folder path template</span>
                      <input
                        type="text"
                        value={ydFolderPathTemplate}
                        onChange={(e) => setYdFolderPathTemplate(e.target.value)}
                        placeholder="/Video/{{ display_name }}"
                        className={FILTER_CONTROL}
                      />
                    </div>
                    <div className="space-y-1.5">
                      <span className={FILTER_LABEL}>Filename template</span>
                      <input
                        type="text"
                        value={ydFilenameTemplate}
                        onChange={(e) => setYdFilenameTemplate(e.target.value)}
                        placeholder="{{ display_name }}.mp4"
                        className={FILTER_CONTROL}
                      />
                    </div>
                    <div className="flex gap-6">
                      <label className="flex cursor-pointer items-center gap-2.5">
                        <input
                          type="checkbox"
                          checked={ydOverwrite}
                          onChange={(e) => setYdOverwrite(e.target.checked)}
                          className="accent-[#224C87]"
                        />
                        <span className="text-sm text-gray-700">Overwrite existing</span>
                      </label>
                      <label className="flex cursor-pointer items-center gap-2.5">
                        <input
                          type="checkbox"
                          checked={ydPublish}
                          onChange={(e) => setYdPublish(e.target.checked)}
                          className="accent-[#224C87]"
                        />
                        <span className="text-sm text-gray-700">Publish publicly</span>
                      </label>
                    </div>
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
            <p className="flex-1 truncate text-xs text-red-500" title={runError}>
              {runError}
            </p>
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
            {runMutation.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Play size={14} />
            )}
            Run
          </button>
        </div>
      </div>
    </div>
  );
}
