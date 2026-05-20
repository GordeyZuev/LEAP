"use client";

import { use, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Save, Play, FlaskConical, Clock, Copy, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/api/client";
import { TagInput } from "@/components/ui/tag-input";
import { TemplateField } from "@/components/platforms/platform-fields";
import { Toast } from "@/components/ui/toast";
import { FILTER_CONTROL } from "@/lib/filter-field-classes";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useTimezones } from "@/hooks/use-references";
import { useToast } from "@/hooks/use-toast";

type ScheduleMode = "visual" | "cron";

interface AutomationFilters {
  exclude_blank: boolean;
  status: string[];
}

interface AutomationProcessingConfig {
  enable_transcription: boolean;
  enable_topics: boolean;
  enable_subtitles: boolean;
  language: string;
  granularity: string;
  prompt: string;
  allow_errors: boolean;
  questions_count: number;
  vocabulary: string[];
}

interface JobForm {
  name: string;
  description: string;
  template_ids: number[];
  schedule_mode: ScheduleMode;
  weekdays: number[];
  time: string;
  timezone: string;
  cron_expression: string;
  sync_days: number;
  is_active: boolean;
  filters: AutomationFilters;
  processing_config_enabled: boolean;
  processing_config: AutomationProcessingConfig;
}

interface TemplateItem {
  id: number;
  name: string;
  is_draft: boolean;
}

interface ApiSchedule {
  type?: string;
  expression?: string;
  hours?: number;
  time?: string;
  days?: number[];
  timezone?: string;
}

interface AutomationJobApi {
  id: number;
  name: string;
  description?: string | null;
  template_ids?: number[];
  schedule?: ApiSchedule;
  sync_config?: { sync_days?: number };
  is_active?: boolean;
  next_run_at?: string | null;
  updated_at?: string;
  filters?: { exclude_blank?: boolean; status?: string[] } | null;
  processing_config?: Record<string, unknown> | null;
}


const WEEKDAY_LABELS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];

const CRON_EXAMPLES = [
  { expr: "0 9 * * *",   desc: "Every day at 9:00" },
  { expr: "0 9 * * 1-5", desc: "Weekdays at 9:00" },
  { expr: "0 */6 * * *", desc: "Every 6 hours" },
  { expr: "0 0 * * *",   desc: "Every night at 0:00" },
];

const DEFAULT_PROCESSING_CONFIG: AutomationProcessingConfig = {
  enable_transcription: true,
  enable_topics: true,
  enable_subtitles: true,
  language: "ru",
  granularity: "medium",
  prompt: "",
  allow_errors: false,
  questions_count: 5,
  vocabulary: [],
};

const DEFAULT_FORM: JobForm = {
  name: "",
  description: "",
  template_ids: [],
  schedule_mode: "visual",
  weekdays: [0, 1, 2, 3, 4],
  time: "09:00",
  timezone: "Europe/Moscow",
  cron_expression: "0 9 * * *",
  sync_days: 2,
  is_active: true,
  filters: { exclude_blank: false, status: [] },
  processing_config_enabled: false,
  processing_config: { ...DEFAULT_PROCESSING_CONFIG },
};

function apiJobToForm(job: AutomationJobApi): JobForm {
  const s = job.schedule;
  let schedule_mode: ScheduleMode = "visual";
  let weekdays = [0, 1, 2, 3, 4];
  let time = "09:00";
  let cron_expression = "0 9 * * *";
  const timezone = s?.timezone ?? "Europe/Moscow";

  if (s?.type === "weekdays") {
    schedule_mode = "visual";
    weekdays = s.days ?? [0, 1, 2, 3, 4];
    time = s.time ?? "09:00";
  } else if (s?.type === "time_of_day") {
    schedule_mode = "visual";
    weekdays = [0, 1, 2, 3, 4, 5, 6];
    time = s.time ?? "09:00";
  } else if (s?.type === "hours") {
    schedule_mode = "cron";
    cron_expression = `0 */${s.hours ?? 4} * * *`;
  } else if (s?.type === "cron") {
    schedule_mode = "cron";
    cron_expression = s.expression ?? "0 9 * * *";
  }

  const pc = job.processing_config as Record<string, unknown> | null | undefined;
  const t = pc?.transcription as Record<string, unknown> | undefined;

  return {
    name: job.name ?? "",
    description: job.description ?? "",
    template_ids: job.template_ids ?? [],
    schedule_mode,
    weekdays,
    time,
    timezone,
    cron_expression,
    sync_days: job.sync_config?.sync_days ?? 2,
    is_active: job.is_active ?? true,
    filters: {
      exclude_blank: job.filters?.exclude_blank ?? false,
      status: job.filters?.status ?? [],
    },
    processing_config_enabled: !!pc,
    processing_config: {
      enable_transcription: (t?.enable_transcription as boolean | undefined) ?? true,
      enable_topics: (t?.enable_topics as boolean | undefined) ?? true,
      enable_subtitles: (t?.enable_subtitles as boolean | undefined) ?? true,
      language: (t?.language as string | undefined) ?? "ru",
      granularity: (t?.granularity as string | undefined) ?? "medium",
      prompt: (t?.prompt as string | undefined) ?? "",
      allow_errors: (t?.allow_errors as boolean | undefined) ?? false,
      questions_count: (t?.questions_count as number | undefined) ?? 5,
      vocabulary: (t?.vocabulary as string[] | undefined) ?? [],
    },
  };
}

function formToSchedule(f: JobForm): ApiSchedule {
  if (f.schedule_mode === "visual") {
    return {
      type: "weekdays",
      days: [...f.weekdays].sort((a, b) => a - b),
      time: f.time,
      timezone: f.timezone,
    };
  }
  return {
    type: "cron",
    expression: f.cron_expression.trim(),
    timezone: f.timezone,
  };
}

function formatNextRun(iso: string): string {
  return new Date(iso).toLocaleString("ru-RU", {
    day: "numeric",
    month: "long",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatSyncWindowStart(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
}

function getSyncDaysWarning(f: JobForm): string | null {
  if (f.schedule_mode !== "visual" || f.weekdays.length < 2) return null;
  const sorted = [...f.weekdays].sort((a, b) => a - b);
  let maxGap = 0;
  for (let i = 1; i < sorted.length; i++) maxGap = Math.max(maxGap, sorted[i] - sorted[i - 1]);
  maxGap = Math.max(maxGap, 7 - sorted[sorted.length - 1] + sorted[0]);
  if (f.sync_days < maxGap) {
    return `Max gap between runs (${maxGap} d) exceeds the search window (${f.sync_days} d) — some recordings may be missed. Increase the window to ${maxGap}+ d.`;
  }
  return null;
}

export default function AutomationJobPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const isNew = id === "new";

  const { data: existing, isPending, isError } = useQuery({
    queryKey: ["automation-job", id],
    queryFn: async () => (await apiClient.get<AutomationJobApi>(`/automation/jobs/${id}`)).data,
    enabled: !isNew,
  });

  const { data: templatesData } = useQuery<{ items: TemplateItem[] }>({
    queryKey: ["templates"],
    queryFn: async () => (await apiClient.get("/templates?per_page=50")).data,
  });

  const templates = (templatesData?.items ?? []).filter((t) => !t.is_draft);

  if (!isNew && isPending) return <div className="p-8 text-sm text-gray-400">Loading…</div>;
  if (!isNew && isError) {
    return (
      <div className="p-8 space-y-2">
        <p className="text-sm text-red-500">Failed to load job</p>
        <Link href="/automation" className="text-sm text-[#224C87] hover:underline">← Back</Link>
      </div>
    );
  }

  return (
    <AutomationJobEditor
      key={isNew ? "automation-new" : `automation-${id}-${existing!.updated_at}`}
      jobId={id}
      isNew={isNew}
      initialForm={isNew ? { ...DEFAULT_FORM } : apiJobToForm(existing!)}
      initialNextRunAt={isNew ? null : (existing!.next_run_at ?? null)}
      templates={templates}
      headerTitle={isNew ? "New job" : existing!.name}
    />
  );
}

interface EditorProps {
  jobId: string;
  isNew: boolean;
  initialForm: JobForm;
  initialNextRunAt: string | null;
  templates: TemplateItem[];
  headerTitle: string;
}

function AutomationJobEditor({ jobId, isNew, initialForm, initialNextRunAt, templates, headerTitle }: EditorProps) {
  const router = useRouter();
  const qc = useQueryClient();
  const { data: timezones = [] } = useTimezones();

  const [form, setForm] = useState<JobForm>(() => ({ ...initialForm }));
  const [nextRunAt, setNextRunAt] = useState<string | null>(initialNextRunAt);
  const { toast, show: showFeedback, dismiss: dismissToast } = useToast(5000);

  const savedSnapshot = useRef<string>(JSON.stringify(initialForm));
  const [confirmCopy, setConfirmCopy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmLeave, setConfirmLeave] = useState(false);
  const [pendingHref, setPendingHref] = useState("");

  const save = useMutation<AutomationJobApi, unknown, JobForm>({
    mutationFn: async (data: JobForm) => {
      const body: Record<string, unknown> = {
        name: data.name,
        description: data.description || undefined,
        template_ids: data.template_ids,
        schedule: formToSchedule(data),
        sync_config: { sync_days: data.sync_days },
        is_active: data.is_active,
        filters: {
          exclude_blank: data.filters.exclude_blank,
          ...(data.filters.status.length > 0 ? { status: data.filters.status } : {}),
        },
        processing_config: data.processing_config_enabled
          ? {
              transcription: {
                enable_transcription: data.processing_config.enable_transcription,
                enable_topics: data.processing_config.enable_topics,
                enable_subtitles: data.processing_config.enable_subtitles,
                language: data.processing_config.language,
                granularity: data.processing_config.granularity,
                ...(data.processing_config.prompt ? { prompt: data.processing_config.prompt } : {}),
                allow_errors: data.processing_config.allow_errors,
                questions_count: data.processing_config.questions_count,
                ...(data.processing_config.vocabulary.length > 0 ? { vocabulary: data.processing_config.vocabulary } : {}),
              },
            }
          : null,
      };
      if (isNew) return (await apiClient.post<AutomationJobApi>("/automation/jobs", body)).data;
      return (await apiClient.patch<AutomationJobApi>(`/automation/jobs/${jobId}`, body)).data;
    },
    onSuccess: (result, savedForm) => {
      savedSnapshot.current = JSON.stringify(savedForm);
      qc.invalidateQueries({ queryKey: ["automation-jobs"] });
      showFeedback("success", "Job saved");
      if (result?.next_run_at) setNextRunAt(result.next_run_at);
      if (isNew && result?.id != null) router.push(`/automation/${result.id}`);
      else qc.invalidateQueries({ queryKey: ["automation-job", jobId] });
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      const msg =
        typeof detail === "string" ? detail
        : Array.isArray(detail) ? detail.map((x: { msg?: string }) => x.msg ?? JSON.stringify(x)).join("; ")
        : "Failed to save job";
      showFeedback("error", msg);
    },
  });

  const runNow = useMutation({
    mutationFn: () => apiClient.post(`/automation/jobs/${jobId}/run`),
    onSuccess: () => showFeedback("success", "Job started"),
    onError: () => showFeedback("error", "Failed to start job"),
  });

  const dryRun = useMutation({
    mutationFn: () => apiClient.post(`/automation/jobs/${jobId}/run?dry_run=true`),
    onSuccess: () =>
      showFeedback("info", "Dry run started — preview without real changes. Results will appear in logs.", 7000),
    onError: () => showFeedback("error", "Failed to start dry run"),
  });

  const copyJob = useMutation({
    mutationFn: () =>
      apiClient.post<{ id: number }>(`/automation/jobs/${jobId}/copy`).then((r) => r.data),
    onSuccess: (result) => router.push(`/automation/${result.id}`),
    onError: () => showFeedback("error", "Failed to copy job"),
  });

  const deleteJob = useMutation({
    mutationFn: () => apiClient.delete(`/automation/jobs/${jobId}`),
    onSuccess: () => router.push("/automation"),
    onError: () => showFeedback("error", "Failed to delete job"),
  });

  function toggleWeekday(day: number) {
    setForm((f) => ({
      ...f,
      weekdays: f.weekdays.includes(day) ? f.weekdays.filter((d) => d !== day) : [...f.weekdays, day],
    }));
  }

  function toggleTemplate(tid: number) {
    setForm((f) => ({
      ...f,
      template_ids: f.template_ids.includes(tid)
        ? f.template_ids.filter((x) => x !== tid)
        : [...f.template_ids, tid],
    }));
  }

  const syncWarning = getSyncDaysWarning(form);
  const today = new Date().toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
  const syncStart = formatSyncWindowStart(form.sync_days);

  const canSave =
    !!form.name &&
    form.template_ids.length > 0 &&
    (form.schedule_mode !== "visual" || form.weekdays.length > 0);

  const isDirty = JSON.stringify(form) !== savedSnapshot.current;

  return (
    <div className="w-full min-w-0 p-6 sm:p-8">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6 flex-wrap">
        <button
          type="button"
          onClick={() => {
            if (isDirty) { setPendingHref("/automation"); setConfirmLeave(true); }
            else router.push("/automation");
          }}
          className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700 transition-colors"
        >
          <ArrowLeft size={16} /> Automation
        </button>
        <span className="text-gray-300">/</span>
        <h1 className="text-lg font-semibold text-gray-900 flex-1 min-w-0 truncate">{headerTitle}</h1>

        {!isNew && (
          <button
            type="button"
            onClick={() => dryRun.mutate()}
            disabled={dryRun.isPending}
            title="Run without real changes"
            className="flex items-center gap-2 px-4 py-2 rounded-xl border border-[#D9D9D9] text-sm font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50 transition-colors"
          >
            <FlaskConical size={15} />
            {dryRun.isPending ? "Checking…" : "Dry run"}
          </button>
        )}

        {!isNew && (
          <button
            type="button"
            onClick={() => runNow.mutate()}
            disabled={runNow.isPending}
            className="flex items-center gap-2 px-4 py-2 rounded-xl border border-[#D9D9D9] text-sm font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50 transition-colors"
          >
            <Play size={15} />
            {runNow.isPending ? "Running…" : "Run now"}
          </button>
        )}

        {!isNew && (
          <button
            type="button"
            onClick={() => setConfirmCopy(true)}
            disabled={copyJob.isPending}
            title="Create a copy of the job"
            className="flex items-center gap-2 px-4 py-2 rounded-xl border border-[#D9D9D9] text-sm font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50 transition-colors"
          >
            <Copy size={15} />
            {copyJob.isPending ? "Copying…" : "Copy"}
          </button>
        )}

        {!isNew && (
          <button
            type="button"
            onClick={() => setConfirmDelete(true)}
            disabled={deleteJob.isPending}
            title="Delete job"
            className="flex items-center gap-2 px-4 py-2 rounded-xl border border-red-200 text-sm font-medium text-red-500 hover:bg-red-50 disabled:opacity-50 transition-colors"
          >
            <Trash2 size={15} />
            Delete
          </button>
        )}

        <button
          type="button"
          onClick={() => save.mutate(form)}
          disabled={save.isPending || !canSave}
          className="flex items-center gap-2 bg-[#224C87] text-white px-4 py-2 rounded-xl text-sm font-medium hover:bg-[#1a3d6e] disabled:opacity-50 transition-colors"
        >
          <Save size={15} />
          {save.isPending ? "Saving…" : "Save"}
        </button>
      </div>


      <div className="space-y-5">
        {/* Basic info */}
        <div className="bg-white rounded-2xl border border-[#D9D9D9] shadow-sm p-5 space-y-4">
          <F label="Name *">
            <input
              type="text"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="Daily sync"
              className={inp}
            />
          </F>
          <F label="Description">
            <input
              type="text"
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              placeholder="Optional"
              className={inp}
            />
          </F>
          <Toggle label="Active" checked={form.is_active} onChange={(v) => setForm((f) => ({ ...f, is_active: v }))} />
        </div>

        {/* Templates */}
        <div className="bg-white rounded-2xl border border-[#D9D9D9] shadow-sm p-5 space-y-3">
          <h2 className="text-sm font-semibold text-gray-700">Templates *</h2>
          {templates.length === 0 ? (
            <p className="text-sm text-gray-400">
              No templates.{" "}
              <Link href="/templates/new" className="text-[#224C87] hover:underline">Create →</Link>
            </p>
          ) : (
            <div className="space-y-2">
              {templates.map((t) => (
                <label
                  key={t.id}
                  className="flex items-center gap-3 p-3 rounded-xl border border-[#D9D9D9] cursor-pointer hover:bg-gray-50 transition-colors"
                >
                  <input
                    type="checkbox"
                    checked={form.template_ids.includes(t.id)}
                    onChange={() => toggleTemplate(t.id)}
                    className="rounded accent-[#224C87]"
                  />
                  <span className="text-sm font-medium text-gray-900">{t.name}</span>
                </label>
              ))}
            </div>
          )}
          {form.template_ids.length === 0 && templates.length > 0 && (
            <p className="text-xs text-orange-500">Select at least one template</p>
          )}
        </div>

        {/* Filters */}
        <div className="bg-white rounded-2xl border border-[#D9D9D9] shadow-sm p-5 space-y-4">
          <h2 className="text-sm font-semibold text-gray-700">Filters</h2>
          <Toggle
            label="Exclude blank recordings"
            checked={form.filters.exclude_blank}
            onChange={(v) => setForm((f) => ({ ...f, filters: { ...f.filters, exclude_blank: v } }))}
          />
          <F label="Recording statuses" hint="Process only recordings in selected statuses (empty = all)">
            <div className="mt-1 space-y-1.5">
              {(["INITIALIZED", "DOWNLOADED", "TRANSCRIBED", "READY", "FAILED"] as const).map((s) => (
                <label key={s} className="flex items-center gap-2.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={form.filters.status.includes(s)}
                    onChange={(e) => {
                      const next = e.target.checked
                        ? [...form.filters.status, s]
                        : form.filters.status.filter((x) => x !== s);
                      setForm((f) => ({ ...f, filters: { ...f.filters, status: next } }));
                    }}
                    className="rounded accent-[#224C87]"
                  />
                  <span className="text-sm text-gray-700">{s}</span>
                </label>
              ))}
            </div>
          </F>
        </div>

        {/* Processing config */}
        <div className="bg-white rounded-2xl border border-[#D9D9D9] shadow-sm p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-700">Processing config</h2>
            <Toggle
              label=""
              checked={form.processing_config_enabled}
              onChange={(v) => setForm((f) => ({ ...f, processing_config_enabled: v }))}
            />
          </div>
          {!form.processing_config_enabled && (
            <p className="text-xs text-gray-400">Template settings are used. Enable to override.</p>
          )}
          {form.processing_config_enabled && (
            <div className="space-y-4">
              <Toggle
                label="Enable transcription"
                checked={form.processing_config.enable_transcription}
                onChange={(v) => setForm((f) => ({ ...f, processing_config: { ...f.processing_config, enable_transcription: v } }))}
              />
              <Toggle
                label="Extract topics"
                checked={form.processing_config.enable_topics}
                onChange={(v) => setForm((f) => ({ ...f, processing_config: { ...f.processing_config, enable_topics: v } }))}
              />
              <Toggle
                label="Generate subtitles"
                checked={form.processing_config.enable_subtitles}
                onChange={(v) => setForm((f) => ({ ...f, processing_config: { ...f.processing_config, enable_subtitles: v } }))}
              />
              <F label="Language">
                <select
                  value={form.processing_config.language}
                  onChange={(e) => setForm((f) => ({ ...f, processing_config: { ...f.processing_config, language: e.target.value } }))}
                  className={cn(inp, "bg-white appearance-none pr-8")}
                >
                  <option value="ru">Русский</option>
                  <option value="en">English</option>
                  <option value="auto">Auto</option>
                </select>
              </F>
              <F label="Topic granularity">
                <select
                  value={form.processing_config.granularity}
                  onChange={(e) => setForm((f) => ({ ...f, processing_config: { ...f.processing_config, granularity: e.target.value } }))}
                  className={cn(inp, "bg-white appearance-none pr-8")}
                >
                  <option value="short">Short</option>
                  <option value="medium">Medium</option>
                  <option value="long">Long</option>
                </select>
              </F>
              <TemplateField
                label="Transcription prompt"
                value={form.processing_config.prompt}
                onChange={(v) => setForm((f) => ({ ...f, processing_config: { ...f.processing_config, prompt: v } }))}
                multiline
                placeholder="University lecture: machine learning, neural networks…"
              />
              <Toggle
                label="Allow transcription errors"
                checked={form.processing_config.allow_errors}
                onChange={(v) => setForm((f) => ({ ...f, processing_config: { ...f.processing_config, allow_errors: v } }))}
              />
              <F label="Questions count" hint="0 = disabled">
                <input
                  type="number"
                  min={0}
                  max={20}
                  value={form.processing_config.questions_count}
                  onChange={(e) => setForm((f) => ({ ...f, processing_config: { ...f.processing_config, questions_count: parseInt(e.target.value, 10) || 0 } }))}
                  className={cn(inp, "w-32")}
                />
              </F>
              <F label="Vocabulary" hint="Domain-specific terms to improve transcription accuracy">
                <TagInput
                  tags={form.processing_config.vocabulary}
                  onChange={(v) => setForm((f) => ({ ...f, processing_config: { ...f.processing_config, vocabulary: v } }))}
                  placeholder="Add term…"
                />
              </F>
            </div>
          )}
        </div>

        {/* Schedule */}
        <div className="bg-white rounded-2xl border border-[#D9D9D9] shadow-sm p-5 space-y-4">
          <h2 className="text-sm font-semibold text-gray-700">Schedule</h2>

          {/* Mode toggle */}
          <div className="flex gap-1 p-1 bg-gray-100 rounded-xl w-fit">
            {(["visual", "cron"] as ScheduleMode[]).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => setForm((f) => ({ ...f, schedule_mode: mode }))}
                className={cn(
                  "px-4 py-1.5 rounded-lg text-sm font-medium transition-colors",
                  form.schedule_mode === mode
                    ? "bg-white text-gray-900 shadow-sm"
                    : "text-gray-500 hover:text-gray-700"
                )}
              >
                {mode === "visual" ? "Visual" : "Cron"}
              </button>
            ))}
          </div>

          {/* Visual mode */}
          {form.schedule_mode === "visual" && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Days</label>
                <div className="flex gap-1.5">
                  {WEEKDAY_LABELS.map((label, i) => (
                    <button
                      key={i}
                      type="button"
                      onClick={() => toggleWeekday(i)}
                      className={cn(
                        "w-10 h-10 rounded-full text-sm font-medium transition-colors select-none",
                        form.weekdays.includes(i)
                          ? "bg-[#224C87] text-white"
                          : "bg-gray-100 text-gray-500 hover:bg-gray-200"
                      )}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                {form.weekdays.length === 0 && (
                  <p className="text-xs text-orange-500 mt-1.5">Select at least one day</p>
                )}
              </div>

              <div className="flex gap-4">
                <F label="Time">
                  <input
                    type="time"
                    value={form.time}
                    onChange={(e) => setForm((f) => ({ ...f, time: e.target.value }))}
                    className={cn(inp, "w-36")}
                  />
                </F>
                <F label="Timezone">
                  <select
                    value={form.timezone}
                    onChange={(e) => setForm((f) => ({ ...f, timezone: e.target.value }))}
                    className={cn(inp, "appearance-none pr-8")}
                  >
                    {timezones.map(({ value, label }) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                </F>
              </div>
            </div>
          )}

          {/* Cron mode */}
          {form.schedule_mode === "cron" && (
            <div className="space-y-3">
              <div className="flex gap-4">
                <F label="Expression">
                  <input
                    type="text"
                    value={form.cron_expression}
                    onChange={(e) => setForm((f) => ({ ...f, cron_expression: e.target.value }))}
                    placeholder="0 9 * * *"
                    className={cn(inp, "font-mono w-48")}
                  />
                </F>
                <F label="Timezone">
                  <select
                    value={form.timezone}
                    onChange={(e) => setForm((f) => ({ ...f, timezone: e.target.value }))}
                    className={cn(inp, "appearance-none pr-8")}
                  >
                    {timezones.map(({ value, label }) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                </F>
              </div>
              <div className="grid grid-cols-2 gap-2">
                {CRON_EXAMPLES.map((ex) => (
                  <button
                    key={ex.expr}
                    type="button"
                    onClick={() => setForm((f) => ({ ...f, cron_expression: ex.expr }))}
                    className="text-left px-3 py-2 rounded-xl border border-[#D9D9D9] hover:bg-gray-50 transition-colors"
                  >
                    <code className="text-xs font-mono text-[#224C87]">{ex.expr}</code>
                    <p className="text-xs text-gray-400 mt-0.5">{ex.desc}</p>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Next run */}
          {nextRunAt && (
            <div className="flex items-center gap-2 px-3 py-2.5 bg-blue-50 border border-blue-100 rounded-xl">
              <Clock size={14} className="text-blue-500 shrink-0" />
              <p className="text-sm text-blue-700">
                Next run: <span className="font-medium">{formatNextRun(nextRunAt)}</span>
              </p>
            </div>
          )}

          {/* Sync window */}
          <div className="border-t border-[#D9D9D9] pt-4 space-y-2">
            <label className="block text-sm font-medium text-gray-700">Recording search window</label>
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-600">Last</span>
              <input
                type="number"
                min={1}
                max={30}
                value={form.sync_days}
                onChange={(e) => setForm((f) => ({ ...f, sync_days: parseInt(e.target.value, 10) || 2 }))}
                className={cn(inp, "w-20")}
              />
              <span className="text-sm text-gray-600">days</span>
            </div>
            <p className="text-xs text-gray-400">
              ↳ recordings from <span className="font-medium">{syncStart}</span> to <span className="font-medium">{today}</span>
            </p>
            {syncWarning && (
              <div className="flex items-start gap-1.5">
                <span className="text-amber-500 text-xs mt-px shrink-0">⚠</span>
                <p className="text-xs text-amber-600">{syncWarning}</p>
              </div>
            )}
          </div>
        </div>
      </div>

      <ConfirmDialog
        open={confirmCopy}
        title="Copy job?"
        description="An inactive copy will be created with the same settings."
        confirmLabel="Create copy"
        onConfirm={() => { setConfirmCopy(false); copyJob.mutate(); }}
        onCancel={() => setConfirmCopy(false)}
      />

      <ConfirmDialog
        open={confirmDelete}
        title="Delete automation job?"
        description="The job will be permanently deleted."
        confirmLabel="Delete"
        danger
        onConfirm={() => { setConfirmDelete(false); deleteJob.mutate(); }}
        onCancel={() => setConfirmDelete(false)}
      />

      <ConfirmDialog
        open={confirmLeave}
        title="Leave without saving?"
        description="Unsaved changes will be lost."
        confirmLabel="Leave"
        cancelLabel="Stay"
        danger
        onConfirm={() => { setConfirmLeave(false); router.push(pendingHref); }}
        onCancel={() => setConfirmLeave(false)}
      />

      {toast && <Toast key={toast.serial} type={toast.type} message={toast.msg} exiting={toast.exiting} onDismiss={dismissToast} />}
    </div>
  );
}

const inp =
  "w-full px-4 py-2.5 rounded-xl border border-[#D9D9D9] text-sm outline-none focus:border-[#224C87] focus:ring-2 focus:ring-[#224C87]/10 transition-colors bg-white";

function F({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1.5">{label}</label>
      {hint && <p className="text-xs text-gray-400 mb-1.5">{hint}</p>}
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
        <span
          className={cn(
            "inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform",
            checked ? "translate-x-6" : "translate-x-1"
          )}
        />
      </button>
    </label>
  );
}
