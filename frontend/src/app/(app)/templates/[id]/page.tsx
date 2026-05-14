"use client";

import { use, useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Save, Eye } from "lucide-react";
import { apiClient } from "@/api/client";
import { TagInput } from "@/components/ui/tag-input";
import { cn } from "@/lib/utils";

// --- Types ---

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
}

interface MetadataConfig {
  title_template: string;
  description_template: string;
}

interface OutputConfig {
  preset_ids: number[];
  auto_upload: boolean;
}

interface TemplateFormData {
  name: string;
  description: string;
  is_draft: boolean;
  matching_rules: MatchingRules;
  processing_config: ProcessingConfig;
  metadata_config: MetadataConfig;
  output_config: OutputConfig;
}

interface SourceItem { id: number; name: string; source_type?: string; }
interface PresetItem { id: number; name: string; platform: string; }
interface RenderPreviewResponse {
  valid: boolean;
  errors: string[];
  rendered_title: string | null;
  rendered_description: string | null;
}

const DEFAULT_FORM: TemplateFormData = {
  name: "",
  description: "",
  is_draft: true,
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
    granularity: "medium",
    transcription_language: "ru",
  },
  metadata_config: {
    title_template: "",
    description_template: "",
  },
  output_config: {
    preset_ids: [],
    auto_upload: false,
  },
};

const TABS = ["Matching", "Processing", "Output", "Metadata"] as const;
type Tab = typeof TABS[number];

const LANGUAGES = [
  { value: "ru", label: "Russian" },
  { value: "en", label: "English" },
  { value: "auto", label: "Auto-detect" },
];

const GRANULARITY_OPTIONS = [
  { value: "short", label: "Short (fewer topics, longer)" },
  { value: "medium", label: "Medium" },
  { value: "long", label: "Long (more topics, shorter)" },
];

// --- Component ---

export default function TemplateEditorPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const isNew = id === "new";
  const router = useRouter();
  const qc = useQueryClient();

  const [activeTab, setActiveTab] = useState<Tab>("Matching");
  const [form, setForm] = useState<TemplateFormData>(DEFAULT_FORM);
  const [saveError, setSaveError] = useState("");
  const [preview, setPreview] = useState<RenderPreviewResponse | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  // Fetch existing template
  const { data: existing } = useQuery({
    queryKey: ["template", id],
    queryFn: async () => {
      const res = await apiClient.get(`/templates/${id}`);
      return res.data;
    },
    enabled: !isNew,
  });

  // Fetch sources for multi-select
  const { data: sourcesData } = useQuery<{ items: SourceItem[] }>({
    queryKey: ["sources-list"],
    queryFn: async () => {
      const res = await apiClient.get("/sources?per_page=50");
      return res.data;
    },
  });

  // Fetch presets for multi-select
  const { data: presetsData } = useQuery<{ items: PresetItem[] }>({
    queryKey: ["presets-list"],
    queryFn: async () => {
      const res = await apiClient.get("/presets?per_page=50");
      return res.data;
    },
  });

  // Populate form from existing template
  useEffect(() => {
    if (!existing) return;
    setForm({
      name: existing.name ?? "",
      description: existing.description ?? "",
      is_draft: existing.is_draft ?? true,
      matching_rules: {
        exact_matches: existing.matching_rules?.exact_matches ?? [],
        keywords: existing.matching_rules?.keywords ?? [],
        patterns: existing.matching_rules?.patterns ?? [],
        source_ids: existing.matching_rules?.source_ids ?? [],
        exclude_keywords: existing.matching_rules?.exclude_keywords ?? [],
        exclude_patterns: existing.matching_rules?.exclude_patterns ?? [],
        case_sensitive: existing.matching_rules?.case_sensitive ?? false,
      },
      processing_config: {
        enable_transcription: existing.processing_config?.enable_transcription ?? true,
        enable_topics: existing.processing_config?.enable_topics ?? true,
        enable_subtitles: existing.processing_config?.enable_subtitles ?? true,
        granularity: existing.processing_config?.granularity ?? "medium",
        transcription_language: existing.processing_config?.transcription_language ?? "ru",
      },
      metadata_config: {
        title_template: existing.metadata_config?.title_template ?? "",
        description_template: existing.metadata_config?.description_template ?? "",
      },
      output_config: {
        preset_ids: existing.output_config?.preset_ids ?? [],
        auto_upload: existing.output_config?.auto_upload ?? false,
      },
    });
  }, [existing]);

  const save = useMutation({
    mutationFn: async (data: TemplateFormData) => {
      const body = {
        name: data.name,
        description: data.description || undefined,
        is_draft: data.is_draft,
        matching_rules: data.matching_rules.keywords.length > 0 || data.matching_rules.exact_matches.length > 0 || data.matching_rules.patterns.length > 0 || data.matching_rules.source_ids.length > 0
          ? data.matching_rules
          : undefined,
        processing_config: data.processing_config,
        metadata_config: data.metadata_config.title_template || data.metadata_config.description_template
          ? data.metadata_config
          : undefined,
        output_config: data.output_config.preset_ids.length > 0 || data.output_config.auto_upload
          ? data.output_config
          : undefined,
      };
      if (isNew) {
        const res = await apiClient.post("/templates", body);
        return res.data;
      } else {
        const res = await apiClient.patch(`/templates/${id}`, body);
        return res.data;
      }
    },
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: ["templates"] });
      setSaveError("");
      if (isNew) router.push(`/templates/${result.id}`);
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string | Array<{ msg: string }> } } })?.response?.data?.detail;
      if (Array.isArray(detail)) {
        setSaveError(detail.map((e) => e.msg).join("; "));
      } else {
        setSaveError(detail ?? "Failed to save template");
      }
    },
  });

  async function handlePreview() {
    setPreviewLoading(true);
    try {
      const res = await apiClient.post<RenderPreviewResponse>("/templates/render-preview", {
        title_template: form.metadata_config.title_template,
        description_template: form.metadata_config.description_template,
      });
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
  function setPC<K extends keyof ProcessingConfig>(key: K, value: ProcessingConfig[K]) {
    setForm((f) => ({ ...f, processing_config: { ...f.processing_config, [key]: value } }));
  }
  function setMC<K extends keyof MetadataConfig>(key: K, value: MetadataConfig[K]) {
    setForm((f) => ({ ...f, metadata_config: { ...f.metadata_config, [key]: value } }));
  }
  function setOC<K extends keyof OutputConfig>(key: K, value: OutputConfig[K]) {
    setForm((f) => ({ ...f, output_config: { ...f.output_config, [key]: value } }));
  }

  const sources = sourcesData?.items ?? [];
  const presets = presetsData?.items ?? [];

  return (
    <div className="p-8 max-w-3xl">
      {/* Header */}
      <div className="flex items-center gap-4 mb-6 flex-wrap">
        <Link href="/templates" className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700 transition-colors">
          <ArrowLeft size={16} /> Templates
        </Link>
        <span className="text-gray-300">/</span>
        <h1 className="text-lg font-semibold text-gray-900 flex-1">
          {isNew ? "New template" : (existing?.name ?? "…")}
        </h1>

        <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
          <input
            type="checkbox"
            checked={form.is_draft}
            onChange={(e) => setForm((f) => ({ ...f, is_draft: e.target.checked }))}
            className="rounded accent-[#224C87]"
          />
          Draft
        </label>

        <button
          onClick={() => save.mutate(form)}
          disabled={save.isPending || !form.name}
          className="flex items-center gap-2 bg-[#224C87] text-white px-4 py-2 rounded-xl text-sm font-medium hover:bg-[#1a3d6e] disabled:opacity-50 transition-colors"
        >
          <Save size={15} />
          {save.isPending ? "Saving…" : "Save"}
        </button>
      </div>

      {saveError && (
        <div className="mb-4 px-4 py-3 bg-red-50 border border-red-200 rounded-xl text-sm text-red-600">{saveError}</div>
      )}

      {/* Name + description */}
      <div className="bg-white rounded-2xl border border-[#D9D9D9] shadow-sm p-5 mb-5 space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1.5">Name *</label>
          <input
            type="text"
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            placeholder="ML Lectures"
            className="w-full px-4 py-2.5 rounded-xl border border-[#D9D9D9] text-sm outline-none focus:border-[#224C87] focus:ring-2 focus:ring-[#224C87]/10 transition-colors"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1.5">Description</label>
          <input
            type="text"
            value={form.description}
            onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            placeholder="Optional description"
            className="w-full px-4 py-2.5 rounded-xl border border-[#D9D9D9] text-sm outline-none focus:border-[#224C87] focus:ring-2 focus:ring-[#224C87]/10 transition-colors"
          />
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-[#D9D9D9] mb-5">
        {TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={cn(
              "px-5 py-2.5 text-sm font-medium transition-colors border-b-2",
              activeTab === tab
                ? "border-[#224C87] text-[#224C87]"
                : "border-transparent text-gray-500 hover:text-gray-700"
            )}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="bg-white rounded-2xl border border-[#D9D9D9] shadow-sm p-6 space-y-5">
        {activeTab === "Matching" && (
          <>
            <Field label="Keywords" hint="Match recordings whose name contains any of these words">
              <TagInput tags={form.matching_rules.keywords} onChange={(v) => setMR("keywords", v)} placeholder="Add keyword…" />
            </Field>
            <Field label="Exact matches" hint="Exact recording name matches">
              <TagInput tags={form.matching_rules.exact_matches} onChange={(v) => setMR("exact_matches", v)} placeholder="Exact name…" />
            </Field>
            <Field label="Regex patterns" hint="Advanced: regex patterns against recording name">
              <TagInput tags={form.matching_rules.patterns} onChange={(v) => setMR("patterns", v)} placeholder="^ML.*" />
            </Field>
            <Field label="Exclude keywords">
              <TagInput tags={form.matching_rules.exclude_keywords} onChange={(v) => setMR("exclude_keywords", v)} placeholder="Skip if contains…" />
            </Field>

            {sources.length > 0 && (
              <Field label="Sources" hint="Only match recordings from these sources">
                <div className="space-y-2">
                  {sources.map((s) => (
                    <label key={s.id} className="flex items-center gap-3 p-3 rounded-xl border border-[#D9D9D9] cursor-pointer hover:bg-gray-50 transition-colors">
                      <input
                        type="checkbox"
                        checked={form.matching_rules.source_ids.includes(s.id)}
                        onChange={(e) => {
                          const ids = e.target.checked
                            ? [...form.matching_rules.source_ids, s.id]
                            : form.matching_rules.source_ids.filter((x) => x !== s.id);
                          setMR("source_ids", ids);
                        }}
                        className="rounded accent-[#224C87]"
                      />
                      <span className="text-sm font-medium text-gray-900 flex-1">{s.name}</span>
                      {s.source_type && <span className="text-xs text-gray-400">{s.source_type}</span>}
                    </label>
                  ))}
                </div>
              </Field>
            )}

            <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
              <input
                type="checkbox"
                checked={form.matching_rules.case_sensitive}
                onChange={(e) => setMR("case_sensitive", e.target.checked)}
                className="rounded accent-[#224C87]"
              />
              Case sensitive matching
            </label>
          </>
        )}

        {activeTab === "Processing" && (
          <>
            <Toggle label="Enable transcription" checked={form.processing_config.enable_transcription} onChange={(v) => setPC("enable_transcription", v)} />
            <Toggle label="Extract topics" checked={form.processing_config.enable_topics} onChange={(v) => setPC("enable_topics", v)} />
            <Toggle label="Generate subtitles" checked={form.processing_config.enable_subtitles} onChange={(v) => setPC("enable_subtitles", v)} />
            <Field label="Language">
              <select
                value={form.processing_config.transcription_language}
                onChange={(e) => setPC("transcription_language", e.target.value)}
                className="w-full px-3 py-2.5 rounded-xl border border-[#D9D9D9] text-sm outline-none focus:border-[#224C87] focus:ring-2 focus:ring-[#224C87]/10 bg-white"
              >
                {LANGUAGES.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
              </select>
            </Field>
            <Field label="Topic granularity">
              <select
                value={form.processing_config.granularity}
                onChange={(e) => setPC("granularity", e.target.value)}
                className="w-full px-3 py-2.5 rounded-xl border border-[#D9D9D9] text-sm outline-none focus:border-[#224C87] focus:ring-2 focus:ring-[#224C87]/10 bg-white"
              >
                {GRANULARITY_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </Field>
          </>
        )}

        {activeTab === "Output" && (
          <>
            {presets.length > 0 && (
              <Field label="Output presets" hint="Apply these presets when uploading">
                <div className="space-y-2">
                  {presets.map((p) => (
                    <label key={p.id} className="flex items-center gap-3 p-3 rounded-xl border border-[#D9D9D9] cursor-pointer hover:bg-gray-50 transition-colors">
                      <input
                        type="checkbox"
                        checked={form.output_config.preset_ids.includes(p.id)}
                        onChange={(e) => {
                          const ids = e.target.checked
                            ? [...form.output_config.preset_ids, p.id]
                            : form.output_config.preset_ids.filter((x) => x !== p.id);
                          setOC("preset_ids", ids);
                        }}
                        className="rounded accent-[#224C87]"
                      />
                      <span className="text-sm font-medium text-gray-900 flex-1">{p.name}</span>
                      <span className="text-xs text-gray-400 capitalize">{p.platform}</span>
                    </label>
                  ))}
                </div>
              </Field>
            )}
            {presets.length === 0 && (
              <p className="text-sm text-gray-400">No presets yet. <Link href="/presets/new" className="text-[#224C87] hover:underline">Create one →</Link></p>
            )}
            <Toggle label="Auto-upload after processing" checked={form.output_config.auto_upload} onChange={(v) => setOC("auto_upload", v)} />
          </>
        )}

        {activeTab === "Metadata" && (
          <>
            <Field label="Title template" hint='Jinja2 template. Variables: {{ display_name }}, {{ date }}, {{ topic }}'>
              <textarea
                value={form.metadata_config.title_template}
                onChange={(e) => setMC("title_template", e.target.value)}
                rows={2}
                placeholder="{{ display_name }} | {{ topic }} ({{ date }})"
                className="w-full px-4 py-2.5 rounded-xl border border-[#D9D9D9] text-sm outline-none focus:border-[#224C87] focus:ring-2 focus:ring-[#224C87]/10 resize-none transition-colors"
              />
            </Field>
            <Field label="Description template">
              <textarea
                value={form.metadata_config.description_template}
                onChange={(e) => setMC("description_template", e.target.value)}
                rows={5}
                placeholder="Recording from {{ date }}\n\nTopics:\n{{ topics }}"
                className="w-full px-4 py-2.5 rounded-xl border border-[#D9D9D9] text-sm outline-none focus:border-[#224C87] focus:ring-2 focus:ring-[#224C87]/10 resize-none transition-colors font-mono text-xs"
              />
            </Field>

            <button
              onClick={handlePreview}
              disabled={previewLoading}
              className="flex items-center gap-2 px-4 py-2 rounded-xl border border-[#D9D9D9] text-sm font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50 transition-colors"
            >
              <Eye size={15} />
              {previewLoading ? "Rendering…" : "Preview render"}
            </button>

            {preview && (
              <div className={cn("p-4 rounded-xl border text-sm", preview.valid ? "bg-green-50 border-green-200" : "bg-red-50 border-red-200")}>
                {preview.errors.length > 0 && (
                  <div className="mb-3">
                    {preview.errors.map((e, i) => <p key={i} className="text-red-600 text-xs">{e}</p>)}
                  </div>
                )}
                {preview.rendered_title && (
                  <div className="mb-2">
                    <p className="text-xs text-gray-500 mb-1">Title:</p>
                    <p className="font-medium text-gray-900">{preview.rendered_title}</p>
                  </div>
                )}
                {preview.rendered_description && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Description:</p>
                    <pre className="text-xs text-gray-700 whitespace-pre-wrap font-sans">{preview.rendered_description}</pre>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1.5">{label}</label>
      {hint && <p className="text-xs text-gray-400 mb-2">{hint}</p>}
      {children}
    </div>
  );
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center justify-between py-2 cursor-pointer">
      <span className="text-sm font-medium text-gray-700">{label}</span>
      <button
        type="button"
        onClick={() => onChange(!checked)}
        className={cn(
          "relative inline-flex h-6 w-11 items-center rounded-full transition-colors",
          checked ? "bg-[#224C87]" : "bg-gray-200"
        )}
      >
        <span className={cn(
          "inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform",
          checked ? "translate-x-6" : "translate-x-1"
        )} />
      </button>
    </label>
  );
}
