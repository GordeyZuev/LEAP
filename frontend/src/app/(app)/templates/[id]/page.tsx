"use client";

import { use, useEffect, useId, useMemo, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Save, Eye, Copy, Trash2, RefreshCw, Users, X, MoreHorizontal, Layers } from "lucide-react";
import { apiClient } from "@/api/client";
import { TagInput } from "@/components/ui/tag-input";
import { Toast } from "@/components/ui/toast";
import { ActionButton } from "@/components/ui/action-button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Modal } from "@/components/ui/modal";
import { Toggle } from "@/components/ui/toggle";
import { Disclosure } from "@/components/ui/disclosure";
import { combinedHasJinjaVar } from "@/lib/jinja-autocomplete";
import {
  ProcessingFields,
  DEFAULT_TRIMMING,
  trimmingFromApi,
  type ProcessingFormFields,
} from "@/components/platforms/processing-fields";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import {
  TemplateField,
  YouTubeFields,
  YandexDiskFields,
  DEFAULT_YOUTUBE_FIELDS,
  DEFAULT_YANDEX_DISK_FIELDS,
  youtubeFieldsFromApi,
  youtubeFieldsToApi,
  yandexFieldsFromApi,
  DEFAULT_LEAP_FIELDS,
  leapFieldsFromApi,
  LeapLookFields,
  type LeapFieldsValue,
  type YouTubeFieldsValue,
  type YandexDiskFieldsValue,
} from "@/components/platforms/platform-fields";
import {
  MetadataPreviewResultBox,
  type MetadataRenderPreviewData,
} from "@/components/platforms/metadata-render-preview";
import {
  DisplayConfigFields,
  type DisplayConfig,
  defaultTopicsDisplay,
  defaultQuestionsDisplay,
  toDisplayPayload,
  fromDisplayPayload,
  appendDisplayConfigPreviewBody,
} from "@/components/platforms/display-config-fields";
import { useGranularities, useLanguages } from "@/hooks/use-references";
import { Field } from "@/components/ui/field";
import { ChecklistPicker } from "@/components/ui/checklist-picker";
import { CreatePlaceholder } from "@/components/ui/create-placeholder";
import { ThumbnailPicker } from "@/components/platforms/thumbnail-picker";
import {
  filterLeapPresets,
  LeapFillFromPresetButton,
  leapPresetMetadataFromApi,
} from "@/components/platforms/leap-config-section";
import { usePresetDetails } from "@/hooks/use-preset-details";
import { OutputSettingsFields } from "@/components/platforms/output-settings-fields";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface MatchingRules {
  exact_matches: string[];
  keywords: string[];
  patterns: string[];
  source_ids: number[];
  exclude_keywords: string[];
  exclude_patterns: string[];
  case_sensitive: boolean;
}

interface ProcessingConfig {
  enable_transcription: boolean;
  enable_topics: boolean;
  enable_subtitles: boolean;
  granularity: string;
  transcription_language: string;
  allow_errors: boolean;
  questions_count: number;
  vocabulary: string[];
  prompt: string;
  trimming: ProcessingFormFields["trimming"];
}

interface MetadataConfig {
  title_template: string;
  description_template: string;
  topics_display: DisplayConfig;
  questions_display: DisplayConfig;
}

interface OutputConfig {
  preset_ids: number[];
  playlist_ids: number[];
  auto_upload: boolean;
  publish_leap: boolean;
  upload_captions: boolean;
}

interface TemplateFormData {
  name: string;
  description: string;
  is_draft: boolean;
  is_active: boolean;
  matching_rules: MatchingRules;
  processing_config: ProcessingConfig;
  metadata_config: MetadataConfig;
  output_config: OutputConfig;
}

interface SourceItem { id: number; name: string; source_type?: string; }
interface PresetItem { id: number; name: string; platform: string; }
interface MatchPreviewRecording {
  id: number;
  display_name: string;
  current_status: string;
  current_is_mapped: boolean;
  will_become_is_mapped: boolean;
  start_time: string;
  rules_match?: boolean;
}

interface MatchPreviewResponse {
  template_name: string;
  total_checked: number;
  will_match_count: number;
  will_match: MatchPreviewRecording[];
}

const DEFAULT_FORM: TemplateFormData = {
  name: "",
  description: "",
  is_draft: true,
  is_active: false,
  matching_rules: {
    exact_matches: [],
    keywords: [],
    patterns: [],
    source_ids: [],
    exclude_keywords: [],
    exclude_patterns: [],
    case_sensitive: false,
  },
  processing_config: {
    enable_transcription: true,
    enable_topics: true,
    enable_subtitles: true,
    granularity: "long",
    transcription_language: "ru",
    allow_errors: false,
    questions_count: 3,
    vocabulary: [],
    prompt: "",
    trimming: { ...DEFAULT_TRIMMING },
  },
  metadata_config: {
    title_template: "",
    description_template: "",
    topics_display: defaultTopicsDisplay(),
    questions_display: defaultQuestionsDisplay(),
  },
  output_config: {
    preset_ids: [],
    playlist_ids: [],
    auto_upload: true,
    publish_leap: true,
    upload_captions: true,
  },
};

const INP = "w-full px-4 py-2.5 rounded-xl border border-border text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/10 transition-colors bg-card";

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function TemplateEditorPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const isNew = id === "new";
  const router = useRouter();
  const qc = useQueryClient();

  const { data: languages = [] } = useLanguages();
  const { data: granularities = [] } = useGranularities();

  const [form, setForm] = useState<TemplateFormData>(DEFAULT_FORM);
  const { toast, show: showToast, dismiss: dismissToast } = useToast();
  const [preview, setPreview] = useState<MetadataRenderPreviewData | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [leapFields, setLeapFields] = useState<LeapFieldsValue>({ ...DEFAULT_LEAP_FIELDS });
  const [ytFields, setYtFields] = useState<YouTubeFieldsValue>({ ...DEFAULT_YOUTUBE_FIELDS });
  const [ydFields, setYdFields] = useState<YandexDiskFieldsValue>({ ...DEFAULT_YANDEX_DISK_FIELDS });
  const [globalThumbnail, setGlobalThumbnail] = useState("");
  const presetDetails = usePresetDetails(form.output_config.preset_ids);

  const yandexBrowseCredentialId = useMemo(() => {
    for (const pid of form.output_config.preset_ids) {
      const preset = presetDetails[pid];
      if (preset?.platform === "yandex_disk" && preset.credential_id) {
        return preset.credential_id;
      }
    }
    return "" as const;
  }, [form.output_config.preset_ids, presetDetails]);

  const [savedSnapshot, setSavedSnapshot] = useState(() =>
    JSON.stringify({
      form: DEFAULT_FORM,
      leapFields: { ...DEFAULT_LEAP_FIELDS },
      ytFields: { ...DEFAULT_YOUTUBE_FIELDS },
      ydFields: { ...DEFAULT_YANDEX_DISK_FIELDS },
      globalThumbnail: "",
    }),
  );
  const [confirmCopy, setConfirmCopy] = useState(false);
  const [confirmPromote, setConfirmPromote] = useState(false);
  const [promoteMode, setPromoteMode] = useState<"with-save" | "instant">("with-save");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmLeave, setConfirmLeave] = useState(false);
  const [pendingHref, setPendingHref] = useState("");
  const [headerMenuOpen, setHeaderMenuOpen] = useState(false);
  const headerMenuRef = useRef<HTMLDivElement>(null);
  const [updateBaseOnSave, setUpdateBaseOnSave] = useState(false);
  const [baseUpdatePending, setBaseUpdatePending] = useState(false);
  const matchPreviewTitleId = useId();
  const [matchPreviewOpen, setMatchPreviewOpen] = useState(false);
  const [matchPreviewData, setMatchPreviewData] = useState<MatchPreviewResponse | null>(null);
  const [matchPreviewLoading, setMatchPreviewLoading] = useState(false);

  const { data: existing } = useQuery({
    queryKey: ["template", id],
    queryFn: async () => (await apiClient.get(`/templates/${id}`)).data,
    enabled: !isNew,
  });
  const isDefault = !isNew && existing?.is_default === true;

  const { data: sourcesData } = useQuery<{ items: SourceItem[] }>({
    queryKey: ["sources-list"],
    queryFn: async () => (await apiClient.get("/sources?per_page=50")).data,
  });

  const { data: presetsData } = useQuery<{ items: PresetItem[] }>({
    queryKey: ["presets-list"],
    queryFn: async () => (await apiClient.get("/presets?per_page=50")).data,
  });

  /* eslint-disable react-hooks/set-state-in-effect -- hydrate form from fetched template */
  useEffect(() => {
    if (!existing) return;
    const mc = existing.metadata_config;
    const newForm: TemplateFormData = {
      name: existing.name ?? "",
      description: existing.description ?? "",
      is_draft: existing.is_draft ?? true,
      is_active: existing.is_active ?? false,
      matching_rules: {
        exact_matches: existing.matching_rules?.exact_matches ?? [],
        keywords: existing.matching_rules?.keywords ?? [],
        patterns: existing.matching_rules?.patterns ?? [],
        source_ids: existing.matching_rules?.source_ids ?? [],
        exclude_keywords: existing.matching_rules?.exclude_keywords ?? [],
        exclude_patterns: existing.matching_rules?.exclude_patterns ?? [],
        case_sensitive: existing.matching_rules?.case_sensitive ?? false,
      },
      processing_config: (() => {
        const pc = existing.processing_config?.transcription;
        return {
          enable_transcription: pc?.enable_transcription ?? true,
          enable_topics: pc?.enable_topics ?? true,
          enable_subtitles: pc?.enable_subtitles ?? true,
          granularity: pc?.granularity ?? "long",
          transcription_language: pc?.language ?? "ru",
          allow_errors: pc?.allow_errors ?? false,
          questions_count: pc?.questions_count ?? 3,
          vocabulary: pc?.vocabulary ?? [],
          prompt: typeof pc?.prompt === "string" ? pc.prompt : "",
          trimming: trimmingFromApi(existing.processing_config?.trimming),
        };
      })(),
      metadata_config: {
        title_template: mc?.title_template ?? "",
        description_template: mc?.description_template ?? "",
        topics_display: fromDisplayPayload(mc?.topics_display, "topics"),
        questions_display: fromDisplayPayload(mc?.questions_display, "questions"),
      },
      output_config: {
        preset_ids: existing.output_config?.preset_ids ?? [],
        playlist_ids: existing.output_config?.playlist_ids ?? [],
        auto_upload: existing.output_config?.auto_upload ?? false,
        publish_leap: existing.output_config?.publish_leap ?? true,
        upload_captions: existing.output_config?.upload_captions ?? true,
      },
    };
    const newLeapFields = leapFieldsFromApi(mc?.leap);
    const newYtFields = youtubeFieldsFromApi(mc?.youtube);
    const newYdFields = yandexFieldsFromApi(mc?.yandex_disk);
    const newGlobalThumbnail = mc?.thumbnail_name ?? "";
    setForm(newForm);
    setLeapFields(newLeapFields);
    setYtFields(newYtFields);
    setYdFields(newYdFields);
    setGlobalThumbnail(newGlobalThumbnail);
    setSavedSnapshot(JSON.stringify({ form: newForm, leapFields: newLeapFields, ytFields: newYtFields, ydFields: newYdFields, globalThumbnail: newGlobalThumbnail }));
  }, [existing]);
  /* eslint-enable react-hooks/set-state-in-effect */

  // ---------------------------------------------------------------------------
  // Mutations
  // ---------------------------------------------------------------------------

  const save = useMutation({
    mutationFn: async (data: TemplateFormData) => {
      const yt = youtubeFieldsToApi(ytFields);

      const yd: Record<string, unknown> = {};
      if (ydFields.folder_path_template) yd.folder_path_template = ydFields.folder_path_template;
      if (ydFields.filename_template) yd.filename_template = ydFields.filename_template;
      if (ydFields.overwrite) yd.overwrite = true;
      if (ydFields.publish) yd.publish = true;

      const leap: Record<string, unknown> = {};
      if (leapFields.title_template) leap.title_template = leapFields.title_template;
      if (leapFields.description_template) leap.description_template = leapFields.description_template;
      if (leapFields.thumbnail_name) leap.thumbnail_name = leapFields.thumbnail_name;
      if (leapFields.auto_share !== null) leap.auto_share = leapFields.auto_share;

      const metaConfig: Record<string, unknown> = {
        title_template: data.metadata_config.title_template || undefined,
        description_template: data.metadata_config.description_template || undefined,
      };
      const tdPayload = toDisplayPayload(data.metadata_config.topics_display, "topics");
      if (tdPayload) metaConfig.topics_display = tdPayload;
      const qdPayload = toDisplayPayload(data.metadata_config.questions_display, "questions");
      if (qdPayload) metaConfig.questions_display = qdPayload;

      const presetList = presetsData?.items ?? [];
      const selectedPlatform = (platform: string) =>
        data.output_config.preset_ids.some((id) => presetList.find((p) => p.id === id)?.platform === platform);
      const prevMc = (existing?.metadata_config ?? {}) as Record<string, unknown>;
      if (selectedPlatform("youtube")) {
        if (Object.keys(yt).length > 0) metaConfig.youtube = yt;
      } else if (prevMc.youtube) {
        metaConfig.youtube = prevMc.youtube;
      }
      if (selectedPlatform("yandex_disk")) {
        if (Object.keys(yd).length > 0) metaConfig.yandex_disk = yd;
      } else if (prevMc.yandex_disk) {
        metaConfig.yandex_disk = prevMc.yandex_disk;
      }
      if (selectedPlatform("leap")) {
        if (Object.keys(leap).length > 0) metaConfig.leap = leap;
      } else if (prevMc.leap) {
        metaConfig.leap = prevMc.leap;
      }
      if (prevMc.vk) metaConfig.vk = prevMc.vk;
      if (globalThumbnail) metaConfig.thumbnail_name = globalThumbnail;
      const hasMetadata = Object.values(metaConfig).some((v) => v != null);

      const body = {
        name: data.name,
        description: data.description || undefined,
        matching_rules: isDefault
          ? undefined
          : data.matching_rules.keywords.length > 0 ||
              data.matching_rules.exact_matches.length > 0 ||
              data.matching_rules.patterns.length > 0 ||
              data.matching_rules.source_ids.length > 0
            ? data.matching_rules
            : undefined,
        ...(isDefault
          ? {}
          : {
              is_draft: isNew && updateBaseOnSave ? false : data.is_draft,
              is_active: isNew && updateBaseOnSave ? true : data.is_active,
            }),
        processing_config: {
          transcription: {
            enable_transcription: data.processing_config.enable_transcription,
            enable_topics: data.processing_config.enable_topics,
            enable_subtitles: data.processing_config.enable_subtitles,
            granularity: data.processing_config.granularity,
            language: data.processing_config.transcription_language || undefined,
            allow_errors: data.processing_config.allow_errors,
            questions_count: data.processing_config.questions_count,
            vocabulary: data.processing_config.vocabulary.length > 0 ? data.processing_config.vocabulary : undefined,
            prompt: data.processing_config.prompt.trim() || undefined,
          },
          trimming: data.processing_config.trimming,
        },
        metadata_config: hasMetadata ? metaConfig : undefined,
        output_config:
          data.output_config.preset_ids.length > 0
          || data.output_config.auto_upload
          || data.output_config.playlist_ids.length > 0
            ? data.output_config
            : undefined,
      };
      if (isNew) return (await apiClient.post("/templates", body)).data;
      return (await apiClient.patch(`/templates/${id}`, body)).data;
    },
    onSuccess: (result, savedForm) => {
      setSavedSnapshot(JSON.stringify({ form: savedForm, leapFields, ytFields, ydFields, globalThumbnail }));
      qc.invalidateQueries({ queryKey: ["templates"] });
      qc.invalidateQueries({ queryKey: ["template", id] });
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string | Array<{ msg: string }> } } })?.response?.data
        ?.detail;
      showToast(
        "error",
        Array.isArray(detail) ? detail.map((e) => e.msg).join("; ") : (detail ?? "Failed to save template"),
      );
    },
  });

  const copyTemplate = useMutation({
    mutationFn: () =>
      apiClient.post<{ id: number }>(`/templates/${id}/copy`).then((r) => r.data),
    onSuccess: (result) => router.push(`/templates/${result.id}`),
    onError: () => showToast("error", "Failed to copy template"),
  });

  const deleteTemplate = useMutation({
    mutationFn: () => apiClient.delete(`/templates/${id}`),
    onSuccess: () => router.push("/templates"),
    onError: () => showToast("error", "Failed to delete template"),
  });

  const rematch = useMutation({
    mutationFn: () => apiClient.post(`/templates/${id}/rematch`),
    onSuccess: () => showToast("success", "Rematch queued"),
    onError: () => showToast("error", "Failed to start rematch"),
  });

  async function handleMatchPreview() {
    setMatchPreviewLoading(true);
    setMatchPreviewData(null);
    setMatchPreviewOpen(true);
    try {
      const res = await apiClient.post<MatchPreviewResponse>(`/templates/${id}/preview`, {
        matching_rules: form.matching_rules,
      });
      setMatchPreviewData(res.data);
    } catch {
      setMatchPreviewOpen(false);
    } finally {
      setMatchPreviewLoading(false);
    }
  }

  async function handlePreview() {
    setPreviewLoading(true);
    try {
      const body: Record<string, unknown> = {
        title_template: form.metadata_config.title_template,
        description_template: form.metadata_config.description_template,
      };
      if (!isNew) {
        body.template_id = Number(id);
      }
      const fp = ydFields.folder_path_template?.trim();
      const fn = ydFields.filename_template?.trim();
      if (fp) body.folder_path_template = fp;
      if (fn) body.filename_template = fn;
      appendDisplayConfigPreviewBody(
        body,
        form.metadata_config.topics_display,
        form.metadata_config.questions_display,
      );
      const res = await apiClient.post<MetadataRenderPreviewData>("/templates/render-preview", body);
      setPreview(res.data);
    } catch {
      setPreview(null);
    } finally {
      setPreviewLoading(false);
    }
  }

  function setMR<K extends keyof MatchingRules>(key: K, value: MatchingRules[K]) {
    setForm((f) => ({ ...f, matching_rules: { ...f.matching_rules, [key]: value } }));
  }
  function setMC<K extends keyof MetadataConfig>(key: K, value: MetadataConfig[K]) {
    setForm((f) => ({ ...f, metadata_config: { ...f.metadata_config, [key]: value } }));
  }
  function setOC<K extends keyof OutputConfig>(key: K, value: OutputConfig[K]) {
    setForm((f) => ({ ...f, output_config: { ...f.output_config, [key]: value } }));
  }

  const sources = sourcesData?.items ?? [];
  const presets = presetsData?.items ?? [];
  const leapPresets = filterLeapPresets(presets);
  const copyPresets = presets.filter((p) => p.platform === "youtube" || p.platform === "yandex_disk");
  const selectedLeapId = form.output_config.preset_ids.find((id) => leapPresets.some((p) => p.id === id)) ?? null;
  const selectedLeapPresetMeta = useMemo(
    () =>
      selectedLeapId != null ? leapPresetMetadataFromApi(presetDetails[selectedLeapId]?.preset_metadata) : null,
    [selectedLeapId, presetDetails],
  );
  const selectedCopyCount = form.output_config.preset_ids.filter((id) =>
    copyPresets.some((p) => p.id === id),
  ).length;

  function setLeapPresetId(id: number | null) {
    const withoutLeap = form.output_config.preset_ids.filter((pid) => !leapPresets.some((p) => p.id === pid));
    const nextPresetIds = id == null ? withoutLeap : [...withoutLeap, id];
    setOC("preset_ids", nextPresetIds);
  }

  // Derived status label
  const statusLabel = isDefault
    ? "Base template"
    : form.is_draft
      ? "Draft"
      : form.is_active
        ? "Active"
        : "Inactive";
  const statusColor = isDefault
    ? "bg-primary/10 text-primary"
    : form.is_draft
    ? "bg-yellow-100 text-yellow-700 dark:bg-yellow-500/15 dark:text-yellow-300"
    : form.is_active
      ? "bg-green-100 text-green-700 dark:bg-green-500/15 dark:text-green-300"
      : "bg-muted text-muted-foreground";

  const isDirty =
    JSON.stringify({ form, leapFields, ytFields, ydFields, globalThumbnail }) !== savedSnapshot;

  async function promoteTemplate(sourceId: number) {
    setBaseUpdatePending(true);
    try {
      await apiClient.post(`/templates/${sourceId}/set-as-default`);
      await qc.invalidateQueries({ queryKey: ["default-template"] });
      await qc.invalidateQueries({ queryKey: ["templates"] });
      await qc.invalidateQueries({ queryKey: ["template", String(sourceId)] });
      setUpdateBaseOnSave(false);
      showToast("success", "Base template updated");
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      showToast("error", detail ?? "Failed to update base template");
      throw err;
    } finally {
      setBaseUpdatePending(false);
    }
  }

  function handleSaveClick() {
    if (!form.name.trim()) return;
    if (form.output_config.auto_upload && selectedCopyCount === 0) {
      showToast("error", "Auto-upload needs a YouTube or Yandex Disk preset.");
      return;
    }
    if (updateBaseOnSave && isNew) {
      setPromoteMode("with-save");
      setConfirmPromote(true);
      return;
    }
    void executeSave(false);
  }

  async function executeSave(withPromote: boolean) {
    if (!form.name.trim()) return;
    if (form.output_config.auto_upload && selectedCopyCount === 0) {
      showToast("error", "Auto-upload needs a YouTube or Yandex Disk preset.");
      return;
    }

    let result: { id: number };
    try {
      result = await save.mutateAsync(form);
    } catch {
      return;
    }

    const sourceId = result.id ?? Number(id);

    if (withPromote) {
      try {
        await promoteTemplate(sourceId);
      } catch {
        if (isNew) router.push(`/templates/${sourceId}`);
        return;
      }
    } else {
      showToast("success", "Template saved");
    }

    if (isNew) {
      router.push(`/templates/${sourceId}`);
    }
  }

  async function executeInstantPromote() {
    let sourceId = Number(id);
    if (isDirty) {
      try {
        const result = await save.mutateAsync(form);
        sourceId = result.id ?? sourceId;
      } catch {
        return;
      }
    }
    await promoteTemplate(sourceId);
  }

  useEffect(() => {
    if (!headerMenuOpen) return;
    const onPointerDown = (e: PointerEvent) => {
      if (headerMenuRef.current && !headerMenuRef.current.contains(e.target as Node)) {
        setHeaderMenuOpen(false);
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [headerMenuOpen]);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="w-full min-w-0 p-6 sm:p-8">
      {/* Header */}
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => {
            if (isDirty) { setPendingHref("/templates"); setConfirmLeave(true); }
            else router.push("/templates");
          }}
          className="flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-secondary-foreground"
        >
          <ArrowLeft size={16} /> Templates
        </button>
        <span className="text-gray-300">/</span>
        <h1 className="min-w-0 flex-1 truncate text-lg font-semibold text-foreground">
          {isNew ? "New template" : (existing?.name ?? "…")}
        </h1>

        <ActionButton
          onClick={handleSaveClick}
          isPending={save.isPending || baseUpdatePending}
          isSuccess={save.isSuccess && !baseUpdatePending}
          disabled={!form.name}
          icon={<Save size={15} />}
          pendingLabel="Saving…"
        >
          Save
        </ActionButton>

        {!isNew && (
          <ActionButton variant="secondary" onClick={() => setConfirmCopy(true)} isPending={copyTemplate.isPending} icon={<Copy size={15} />} pendingLabel="Copying…">
            Copy
          </ActionButton>
        )}

        {!isNew && !isDefault && (
          <div className="relative shrink-0" ref={headerMenuRef}>
            <ActionButton
              variant="secondary"
              onClick={() => setHeaderMenuOpen((v) => !v)}
              aria-expanded={headerMenuOpen}
              aria-haspopup="menu"
              aria-label="More template actions"
              icon={<MoreHorizontal size={15} />}
            >
              More
            </ActionButton>
            {headerMenuOpen && (
              <div
                role="menu"
                className="absolute end-0 top-full z-30 mt-1 w-52 origin-top overflow-hidden rounded-xl border border-border bg-card shadow-lg animate-dropdown-in"
              >
                <TemplateHeaderMenuItem
                  icon={Layers}
                  label="Make base template"
                  onClick={() => {
                    setHeaderMenuOpen(false);
                    setPromoteMode("instant");
                    setConfirmPromote(true);
                  }}
                />
                <TemplateHeaderMenuItem
                  icon={Users}
                  label="Preview matches"
                  onClick={() => {
                    setHeaderMenuOpen(false);
                    void handleMatchPreview();
                  }}
                />
                <TemplateHeaderMenuItem
                  icon={RefreshCw}
                  label="Rematch recordings"
                  onClick={() => {
                    setHeaderMenuOpen(false);
                    rematch.mutate();
                  }}
                />
                <div className="my-1 border-t border-border" role="separator" />
                <TemplateHeaderMenuItem
                  icon={Trash2}
                  label="Delete template"
                  danger
                  onClick={() => {
                    setHeaderMenuOpen(false);
                    setConfirmDelete(true);
                  }}
                />
              </div>
            )}
          </div>
        )}
      </div>

      {/* 2-column layout */}
      <div className="flex flex-col gap-6 lg:flex-row lg:items-start">

        {/* ── Main column ── */}
        <div className="min-w-0 flex-1 space-y-5">

          {/* Basic info */}
          <Section title="General">
            <Field label="Name *">
              <input
                type="text"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="ML Lectures"
                className={INP}
              />
            </Field>
            <Field label="Description">
              <input
                type="text"
                value={form.description}
                onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                placeholder="Optional description"
                className={INP}
              />
            </Field>
          </Section>

          {/* Matching – not used for the always-on base template */}
          {!isDefault && (
          <Section title="Matching rules">
            <Field label="Keywords" hint="Match recordings whose name contains any of these words">
              <TagInput
                tags={form.matching_rules.keywords}
                onChange={(v) => setMR("keywords", v)}
                placeholder="Add keyword…"
              />
            </Field>
            <Field label="Exact matches" hint="Full recording name must equal one of these">
              <TagInput
                tags={form.matching_rules.exact_matches}
                onChange={(v) => setMR("exact_matches", v)}
                placeholder="Exact name…"
              />
            </Field>
            <Field label="Regex patterns" hint="Advanced: regex matched against recording name">
              <TagInput
                tags={form.matching_rules.patterns}
                onChange={(v) => setMR("patterns", v)}
                placeholder="^ML.*"
              />
            </Field>
            <Field label="Exclude keywords">
              <TagInput
                tags={form.matching_rules.exclude_keywords}
                onChange={(v) => setMR("exclude_keywords", v)}
                placeholder="Skip if name contains…"
              />
            </Field>
            <Toggle
              label="Match letter case"
              hint="ML and ml count as different names"
              checked={form.matching_rules.case_sensitive}
              onChange={(v) => setMR("case_sensitive", v)}
            />

            {sources.length > 0 && (
              <Field label="Sources" hint="Only match recordings from these sources">
                <ChecklistPicker
                  title="Select sources"
                  ariaLabel="Sources"
                  emptyLabel="All sources"
                  searchPlaceholder="Search sources"
                  items={sources.map((s) => ({
                    value: s.id,
                    label: s.name,
                    hint: s.source_type,
                    group: s.source_type,
                  }))}
                  value={form.matching_rules.source_ids}
                  onChange={(ids) => setMR("source_ids", ids)}
                />
              </Field>
            )}
          </Section>
          )}

          {isDefault && (
            <div className="rounded-2xl border border-border bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
              This is your account base template. It is always merged first and is not matched or bound to
              recordings – use named templates for auto-assignment.
            </div>
          )}

          {/* Processing */}
          <Section title="Processing">
            <ProcessingFields
              value={{
                enable_transcription: form.processing_config.enable_transcription,
                enable_topics: form.processing_config.enable_topics,
                enable_subtitles: form.processing_config.enable_subtitles,
                language: form.processing_config.transcription_language,
                granularity: form.processing_config.granularity,
                questions_count: form.processing_config.questions_count,
                allow_errors: form.processing_config.allow_errors,
                vocabulary: form.processing_config.vocabulary,
                prompt: form.processing_config.prompt,
                trimming: form.processing_config.trimming,
              }}
              onChange={(patch) =>
                setForm((f) => {
                  const pc = { ...f.processing_config };
                  if (patch.enable_transcription != null) pc.enable_transcription = patch.enable_transcription;
                  if (patch.enable_topics != null) pc.enable_topics = patch.enable_topics;
                  if (patch.enable_subtitles != null) pc.enable_subtitles = patch.enable_subtitles;
                  if (patch.language != null) pc.transcription_language = patch.language;
                  if (patch.granularity != null) pc.granularity = patch.granularity;
                  if (patch.questions_count != null) pc.questions_count = patch.questions_count;
                  if (patch.allow_errors != null) pc.allow_errors = patch.allow_errors;
                  if (patch.vocabulary != null) pc.vocabulary = patch.vocabulary;
                  if (patch.prompt != null) pc.prompt = patch.prompt;
                  if (patch.trimming != null) pc.trimming = patch.trimming;
                  return { ...f, processing_config: pc };
                })
              }
              languages={languages}
              granularities={granularities}
            />
          </Section>

          <Section title="Output">
            <OutputSettingsFields
              publishLeap={form.output_config.publish_leap}
              onPublishLeapChange={(v) => setOC("publish_leap", v)}
              showCourses={!isDefault}
              playlistIds={form.output_config.playlist_ids}
              onPlaylistIdsChange={(ids) => setOC("playlist_ids", ids)}
              leapPresets={leapPresets}
              selectedLeapPresetId={selectedLeapId}
              onLeapPresetIdChange={setLeapPresetId}
              copyPresets={copyPresets}
              selectedCopyPresetIds={form.output_config.preset_ids.filter((id) =>
                copyPresets.some((p) => p.id === id),
              )}
              onSelectedCopyPresetIdsChange={(copyIds) => {
                const leap = form.output_config.preset_ids.filter((id) => leapPresets.some((p) => p.id === id));
                setOC("preset_ids", [...copyIds, ...leap]);
              }}
              autoUpload={form.output_config.auto_upload}
              onAutoUploadChange={(v) => setOC("auto_upload", v)}
              uploadCaptions={form.output_config.upload_captions}
              onUploadCaptionsChange={(v) => setOC("upload_captions", v)}
              autoUploadWarning={
                form.output_config.auto_upload && selectedCopyCount === 0
                  ? "Auto-upload needs a YouTube or Yandex Disk preset."
                  : undefined
              }
            />
          </Section>

          {/* Metadata */}
          <Section title="Metadata templates">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Global</p>

            <ThumbnailPicker
              label="Cover image (all platforms)"
              placeholder="No cover image"
              value={globalThumbnail}
              onChange={setGlobalThumbnail}
            />

            <TemplateField
              label="Title template"
              value={form.metadata_config.title_template}
              onChange={(v) => setMC("title_template", v)}
              placeholder="{{ display_name }} | {{ topic }} ({{ date }})"
            />
            <TemplateField
              label="Description template"
              value={form.metadata_config.description_template}
              onChange={(v) => setMC("description_template", v)}
              multiline
              placeholder={"Recording from {{ date }}\n\nTimestamps:\n{{ topics }}"}
            />

            {combinedHasJinjaVar(
              "topics",
              form.metadata_config.title_template,
              form.metadata_config.description_template,
              leapFields.title_template,
              leapFields.description_template,
              ytFields.title_template,
              ytFields.description_template,
            ) ? (
            <DisplayConfigFields
              kind="topics"
              value={form.metadata_config.topics_display}
              onChange={(patch) =>
                setMC("topics_display", { ...form.metadata_config.topics_display, ...patch })
              }
            />
            ) : null}
            {combinedHasJinjaVar(
              "questions",
              form.metadata_config.title_template,
              form.metadata_config.description_template,
              leapFields.description_template,
              ytFields.description_template,
            ) ? (
            <DisplayConfigFields
              kind="questions"
              value={form.metadata_config.questions_display}
              onChange={(patch) =>
                setMC("questions_display", { ...form.metadata_config.questions_display, ...patch })
              }
            />
            ) : null}

            {selectedLeapId != null
            || copyPresets.some(
              (p) =>
                form.output_config.preset_ids.includes(p.id)
                && (p.platform === "youtube" || p.platform === "yandex_disk"),
            ) ? (
            <>
            <p className="pt-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Platform overrides
            </p>
            <div className="space-y-3">
            {selectedLeapId != null ? (
            <Disclosure title="LEAP">
              <LeapLookFields
                value={leapFields}
                onChange={(patch) => setLeapFields((f) => ({ ...f, ...patch }))}
                showAutoShareOverride
                presetDefaults={selectedLeapPresetMeta}
              />
              <LeapFillFromPresetButton
                metadata={selectedLeapPresetMeta}
                onApply={(patch) => setLeapFields((f) => ({ ...f, ...patch }))}
              />
              <p className="text-xs text-muted-foreground">Empty fields inherit from preset.</p>
            </Disclosure>
            ) : null}
            {copyPresets.some((p) => form.output_config.preset_ids.includes(p.id) && p.platform === "youtube") ? (
            <Disclosure title="YouTube">
              <YouTubeFields
                value={ytFields}
                onChange={(patch) => setYtFields((f) => ({ ...f, ...patch }))}
                showThumbnail
                showMadeForKids
                showExtended
              />
            </Disclosure>
            ) : null}
            {copyPresets.some((p) => form.output_config.preset_ids.includes(p.id) && p.platform === "yandex_disk") ? (
            <Disclosure title="Yandex Disk">
              <YandexDiskFields
                value={ydFields}
                onChange={(patch) => setYdFields((f) => ({ ...f, ...patch }))}
                credentialId={yandexBrowseCredentialId}
              />
            </Disclosure>
            ) : null}
            </div>
            </>
            ) : null}

            <div className="space-y-2 border-t border-border pt-4">
              <p className="text-xs text-muted-foreground">
                Preview uses sample data unless a recording is selected for context.
              </p>
              <ActionButton
                variant="secondary"
                onClick={handlePreview}
                isPending={previewLoading}
                icon={<Eye size={15} />}
                pendingLabel="Rendering…"
              >
                Preview render
              </ActionButton>
              {preview && <MetadataPreviewResultBox preview={preview} />}
            </div>
          </Section>
        </div>

        {/* ── Sidebar ── */}
        <div className="w-full space-y-4 lg:w-72 lg:shrink-0">

          {/* Status & activation */}
          <div className="rounded-2xl border border-border bg-card p-4 shadow-sm">
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Status</h2>

            <div className="mb-4 flex items-center gap-2">
              <span className={cn("inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium", statusColor)}>
                {statusLabel}
              </span>
            </div>

            <div className="space-y-1">
              <div className="my-3 border-t border-border" role="separator" />
              <Toggle
                label="Draft"
                tone="warning"
                checked={isDefault ? false : form.is_draft}
                disabled={isDefault}
                onChange={(next) =>
                  setForm((f) => ({
                    ...f,
                    is_draft: next,
                    is_active: next ? false : f.is_active,
                  }))
                }
                className="rounded-xl px-2 py-2 transition-colors hover:bg-muted"
              />
              <Toggle
                label="Active"
                checked={isDefault ? true : form.is_active}
                disabled={isDefault || form.is_draft}
                onChange={(next) => setForm((f) => ({ ...f, is_active: next }))}
                className="rounded-xl px-2 py-2 transition-colors hover:bg-muted"
              />
              {isNew && (
                <Toggle
                  label="Make base template"
                  checked={updateBaseOnSave}
                  disabled={form.is_draft || !form.is_active}
                  onChange={setUpdateBaseOnSave}
                  className="rounded-xl px-2 py-2 transition-colors hover:bg-muted"
                />
              )}
            </div>

            {!isDefault && form.is_draft && (
              <p className="mt-2 text-[11px] text-muted-foreground">
                Disable Draft to be able to activate the template.
              </p>
            )}
            {isNew && !form.is_draft && !form.is_active && (
              <p className="mt-2 text-[11px] text-muted-foreground">
                Activate the template to make it the base template.
              </p>
            )}
            {isDefault && (
              <p className="mt-2 text-[11px] text-muted-foreground">
                The base template is always active and cannot be deleted. To change it, set another template as
                base.
              </p>
            )}
          </div>

          {/* Info */}
          {!isNew && existing && (
            <div className="rounded-2xl border border-border bg-card p-4 shadow-sm">
              <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Info</h2>
              <div className="space-y-2 text-sm">
                <InfoRow label="Used" value={`${existing.used_count ?? 0}×`} />
                {existing.last_used_at && (
                  <InfoRow
                    label="Last used"
                    value={new Date(existing.last_used_at).toLocaleDateString("en-GB", {
                      day: "numeric",
                      month: "short",
                      year: "numeric",
                    })}
                  />
                )}
                <InfoRow
                  label="Created"
                  value={new Date(existing.created_at).toLocaleDateString("en-GB", {
                    day: "numeric",
                    month: "short",
                    year: "numeric",
                  })}
                />
                <InfoRow
                  label="Updated"
                  value={new Date(existing.updated_at).toLocaleDateString("en-GB", {
                    day: "numeric",
                    month: "short",
                    year: "numeric",
                  })}
                />
              </div>
            </div>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={confirmCopy}
        title="Copy template?"
        description="A new draft copy will be created. You can rename and edit it before activating."
        confirmLabel="Create copy"
        onConfirm={() => { setConfirmCopy(false); copyTemplate.mutate(); }}
        onCancel={() => setConfirmCopy(false)}
      />

      <ConfirmDialog
        open={confirmPromote}
        title="Make base template?"
        description={`«${form.name || "This template"}» will become your base template. The current base template will become a regular template.`}
        confirmLabel="Make base template"
        onConfirm={() => {
          setConfirmPromote(false);
          if (promoteMode === "with-save") void executeSave(true);
          else void executeInstantPromote();
        }}
        onCancel={() => setConfirmPromote(false)}
        isPending={save.isPending || baseUpdatePending}
      />

      <ConfirmDialog
        open={confirmDelete}
        title="Delete template?"
        description="This template will be permanently deleted. Recordings linked to it will be unlinked but not deleted. Automation jobs referencing this template will have it removed automatically."
        confirmLabel="Delete"
        danger
        onConfirm={() => { setConfirmDelete(false); deleteTemplate.mutate(); }}
        onCancel={() => setConfirmDelete(false)}
      />

      <ConfirmDialog
        open={confirmLeave}
        title="Leave without saving?"
        description="You have unsaved changes. They will be lost if you leave."
        confirmLabel="Leave"
        cancelLabel="Stay"
        danger
        onConfirm={() => { setConfirmLeave(false); router.push(pendingHref); }}
        onCancel={() => setConfirmLeave(false)}
      />

      {toast && <Toast key={toast.serial} type={toast.type} message={toast.msg} exiting={toast.exiting} onDismiss={dismissToast} />}

      {/* Match preview modal */}
      <Modal
        open={matchPreviewOpen}
        onClose={() => setMatchPreviewOpen(false)}
        labelledBy={matchPreviewTitleId}
        panelClassName="max-w-lg"
      >
          <div className="flex max-h-[85vh] flex-col">
            <div className="flex items-center justify-between border-b border-border px-5 py-4">
              <h2 id={matchPreviewTitleId} className="text-sm font-semibold text-foreground">Preview matching recordings</h2>
              <button type="button" onClick={() => setMatchPreviewOpen(false)} aria-label="Close dialog" className="text-muted-foreground hover:text-secondary-foreground">
                <X size={16} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-5">
              {matchPreviewLoading && (
                <div className="flex items-center justify-center py-12">
                  <RefreshCw size={20} className="animate-spin text-muted-foreground" />
                </div>
              )}
              {!matchPreviewLoading && matchPreviewData && (
                <>
                  <p className="mb-4 text-xs text-muted-foreground">
                    Checked <span className="font-medium text-secondary-foreground">{matchPreviewData.total_checked}</span> recordings
                    {" "}–{" "}
                    <span className="font-medium text-primary">{matchPreviewData.will_match_count}</span> new matches,
                    {" "}
                    <span className="font-medium text-secondary-foreground">
                      {matchPreviewData.will_match.filter((r) => r.current_is_mapped).length}
                    </span>{" "}
                    already linked.
                  </p>
                  {matchPreviewData.will_match.length === 0 ? (
                    <p className="py-8 text-center text-sm text-muted-foreground">
                      No unmapped skipped recordings match these rules, and none are linked to this template yet.
                    </p>
                  ) : (
                    <div className="divide-y divide-muted">
                      {matchPreviewData.will_match.map((r) => {
                        const rulesMatch = r.rules_match !== false;
                        let badge = "will map";
                        let badgeClass = "bg-muted text-muted-foreground";
                        if (r.current_is_mapped && rulesMatch) {
                          badge = "already linked";
                          badgeClass = "bg-green-50 dark:bg-green-500/10 text-green-700";
                        } else if (r.current_is_mapped && !rulesMatch) {
                          badge = "linked, rules miss";
                          badgeClass = "bg-amber-50 dark:bg-amber-500/10 text-amber-800 dark:text-amber-200";
                        }
                        return (
                        <div key={r.id} className="flex items-center justify-between gap-3 py-2.5">
                          <Link href={`/recordings/${r.id}`} className="min-w-0 flex-1 truncate text-sm font-medium text-foreground hover:text-primary">
                            {r.display_name}
                          </Link>
                          <span className={cn("shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium", badgeClass)}>
                            {badge}
                          </span>
                        </div>
                        );
                      })}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
      </Modal>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function TemplateHeaderMenuItem({
  icon: Icon,
  label,
  onClick,
  danger,
}: {
  icon: React.ComponentType<{ size?: number }>;
  label: string;
  onClick: () => void;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-2 px-3 py-2 text-left text-sm font-medium transition-colors hover:bg-muted",
        danger ? "text-red-600 hover:bg-red-50 dark:hover:bg-red-500/10" : "text-secondary-foreground",
      )}
    >
      <Icon size={15} aria-hidden />
      {label}
    </button>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-4 rounded-2xl border border-border bg-card p-5 shadow-sm">
      <h2 className="text-sm font-semibold text-secondary-foreground">{title}</h2>
      {children}
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium text-foreground">{value}</span>
    </div>
  );
}
