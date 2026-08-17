"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, RefreshCw, Save } from "lucide-react";
import { apiClient } from "@/api/client";
import { cn, extractApiError } from "@/lib/utils";
import { FILTER_CONTROL } from "@/lib/filter-field-classes";
import { ActionButton } from "@/components/ui/action-button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Field } from "@/components/ui/field";
import { NumberInput } from "@/components/ui/number-input";
import { SegmentedField } from "@/components/ui/segmented-field";
import { TagInput } from "@/components/ui/tag-input";
import { Toast } from "@/components/ui/toast";
import { Toggle } from "@/components/ui/toggle";
import { useToast } from "@/hooks/use-toast";
import { useGranularities, useLanguages, useQualities } from "@/hooks/use-references";
import { TOAST_SHORT } from "@/lib/constants";
import { TemplateField } from "@/components/platforms/platform-fields";
import {
  MetadataPreviewResultBox,
  type MetadataRenderPreviewData,
} from "@/components/platforms/metadata-render-preview";
import {
  DisplayConfigFields,
  defaultQuestionsDisplay,
  defaultTopicsDisplay,
  fromDisplayPayload,
  toDisplayPayload,
  appendDisplayConfigPreviewBody,
} from "@/components/platforms/display-config-fields";
import { Collapsible, SectionCard } from "./shared";
import { countChanges, pick } from "./format";
import type {
  ConfigBundle,
  DownloadConfig,
  MetadataConfig,
  RetentionConfig,
  TranscriptionConfig,
  TrimmingConfig,
  UploadConfig,
  UserConfig,
} from "./types";

const DEFAULT_TRIMMING: TrimmingConfig = {
  enable_trimming: true,
  audio_detection: true,
  silence_threshold: -40.0,
  min_silence_duration: 2.0,
  padding_before: 5.0,
  padding_after: 5.0,
};

const DEFAULT_TRANSCRIPTION: TranscriptionConfig = {
  enable_transcription: true,
  language: "ru",
  vocabulary: [],
  allow_errors: false,
  enable_topics: true,
  granularity: "long",
  questions_count: 3,
  enable_subtitles: true,
  enable_translation: false,
  translation_language: "en",
};

const DEFAULT_DOWNLOAD: DownloadConfig = {
  auto_download: false,
  max_file_size_mb: 5000,
  quality: "high",
  retry_attempts: 3,
  retry_delay: 5,
};

const DEFAULT_UPLOAD: UploadConfig = { auto_upload: false, upload_captions: true };

const DEFAULT_METADATA: MetadataConfig = {
  title_template: "{{ display_name }} | {{ topic }} ({{ date }})",
  description_template: "Recording from {{ date }}",
  date_format: "DD.MM.YYYY",
  tags: [],
  topics_display: defaultTopicsDisplay(),
  questions_display: defaultQuestionsDisplay(),
};

const DEFAULT_RETENTION: RetentionConfig = {
  soft_delete_days: 3,
  hard_delete_days: 30,
  auto_expire_days: 90,
};

const TRANSCRIPTION_ADV = [
  "questions_count", "allow_errors", "enable_translation", "translation_language", "vocabulary",
] as const;
const TRIMMING_ADV = [
  "audio_detection", "silence_threshold", "min_silence_duration", "padding_before", "padding_after",
] as const;

export function ProcessingPanel({ onDirtyChange }: { onDirtyChange?: (dirty: boolean) => void }) {
  const qc = useQueryClient();
  const { toast, show: showToast, dismiss: dismissToast } = useToast(TOAST_SHORT);
  const { data: languages = [] } = useLanguages();
  const { data: granularities = [] } = useGranularities();
  const { data: qualities = [] } = useQualities();

  const [trimming, setTrimming] = useState<TrimmingConfig>(DEFAULT_TRIMMING);
  const [transcription, setTranscription] = useState<TranscriptionConfig>(DEFAULT_TRANSCRIPTION);
  const [download, setDownload] = useState<DownloadConfig>(DEFAULT_DOWNLOAD);
  const [upload, setUpload] = useState<UploadConfig>(DEFAULT_UPLOAD);
  const [metadata, setMetadata] = useState<MetadataConfig>(DEFAULT_METADATA);
  const [retention, setRetention] = useState<RetentionConfig>(DEFAULT_RETENTION);

  // Everything starts expanded: this panel is the whole point of the tab, and
  // collapsing by default hid two thirds of it behind five clicks. The sections
  // stay collapsible for anyone who wants to fold one away.
  const [transcriptionAdvOpen, setTranscriptionAdvOpen] = useState(true);
  const [trimmingAdvOpen, setTrimmingAdvOpen] = useState(true);
  const [downloadOpen, setDownloadOpen] = useState(true);
  const [metadataOpen, setMetadataOpen] = useState(true);
  const [retentionOpen, setRetentionOpen] = useState(true);

  // Last server state the form was hydrated from. Everything "unsaved" is
  // measured against this, and it is what Discard restores.
  const [baseline, setBaseline] = useState<ConfigBundle | null>(null);
  const [resetConfirm, setResetConfirm] = useState(false);
  const [preview, setPreview] = useState<MetadataRenderPreviewData | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  const { data: configData } = useQuery<UserConfig>({
    queryKey: ["user-config"],
    queryFn: async () => (await apiClient.get<UserConfig>("/users/me/config")).data,
  });

  const current = useMemo<ConfigBundle>(
    () => ({ trimming, transcription, download, upload, metadata, retention }),
    [trimming, transcription, download, upload, metadata, retention],
  );

  // Per-section tallies so a collapsed section can advertise its own pending
  // edits — collapsing one used to hide them completely.
  const changes = useMemo(() => {
    if (!baseline) {
      return { total: 0, transcriptionAdv: 0, trimmingAdv: 0, download: 0, metadata: 0, retention: 0 };
    }
    return {
      total: countChanges(current, baseline),
      transcriptionAdv: countChanges(
        pick(transcription, TRANSCRIPTION_ADV),
        pick(baseline.transcription, TRANSCRIPTION_ADV),
      ),
      trimmingAdv: countChanges(pick(trimming, TRIMMING_ADV), pick(baseline.trimming, TRIMMING_ADV)),
      download: countChanges(download, baseline.download),
      metadata: countChanges(metadata, baseline.metadata),
      retention: countChanges(retention, baseline.retention),
    };
  }, [baseline, current, transcription, trimming, download, metadata, retention]);

  const dirty = changes.total > 0;

  useEffect(() => { onDirtyChange?.(dirty); }, [dirty, onDirtyChange]);

  // Which payload the form currently reflects. Without it, re-running on a
  // `dirty` flip would re-apply the same config and fight the user's edits.
  const hydratedFrom = useRef<UserConfig | null>(null);

  /* eslint-disable react-hooks/set-state-in-effect -- hydrate local form from fetched config */
  useEffect(() => {
    if (!configData?.config_data) return;
    if (hydratedFrom.current === configData) return;
    // Never clobber edits in progress. staleTime is 30s and refetchOnWindowFocus
    // defaults to true, so without this guard alt-tabbing away and back silently
    // reverted everything the user had typed. Discarding makes the form clean
    // again, and this then adopts whatever the latest fetch brought in.
    if (dirty) return;
    hydratedFrom.current = configData;
    const { trimming: t, transcription: tr, download: d, upload: u, metadata: m, retention: r } =
      configData.config_data;
    const next: ConfigBundle = {
      trimming: { ...DEFAULT_TRIMMING, ...t },
      transcription: { ...DEFAULT_TRANSCRIPTION, ...tr },
      download: { ...DEFAULT_DOWNLOAD, ...d },
      upload: { ...DEFAULT_UPLOAD, ...u },
      metadata: {
        ...DEFAULT_METADATA,
        ...m,
        topics_display: fromDisplayPayload(m?.topics_display, "topics"),
        questions_display: fromDisplayPayload(m?.questions_display, "questions"),
      },
      retention: { ...DEFAULT_RETENTION, ...r },
    };
    setTrimming(next.trimming);
    setTranscription(next.transcription);
    setDownload(next.download);
    setUpload(next.upload);
    setMetadata(next.metadata);
    setRetention(next.retention);
    setBaseline(next);
  }, [configData, dirty]);
  /* eslint-enable react-hooks/set-state-in-effect */

  // Leaving with pending edits loses them — the browser prompt is the only hook
  // that covers tab close and external navigation alike.
  useEffect(() => {
    if (!dirty) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);

  function discardChanges() {
    if (!baseline) return;
    setTrimming(baseline.trimming);
    setTranscription(baseline.transcription);
    setDownload(baseline.download);
    setUpload(baseline.upload);
    setMetadata(baseline.metadata);
    setRetention(baseline.retention);
  }

  const updateConfig = useMutation({
    mutationFn: () =>
      apiClient.patch("/users/me/config", {
        trimming,
        transcription,
        download,
        upload,
        metadata: {
          ...metadata,
          topics_display: toDisplayPayload(metadata.topics_display, "topics"),
          questions_display: toDisplayPayload(metadata.questions_display, "questions"),
        },
        retention,
      }),
    onSuccess: () => {
      // Adopt what we just sent as the new baseline so the form goes clean
      // immediately, rather than staying "unsaved" until the refetch lands.
      setBaseline(current);
      qc.invalidateQueries({ queryKey: ["user-config"] });
      showToast("success", "Settings saved");
    },
    onError: (err) => showToast("error", extractApiError(err), null),
  });

  const resetConfig = useMutation({
    mutationFn: () => apiClient.post("/users/me/config/reset"),
    onSuccess: () => {
      // Let the refetched server config repopulate the form.
      setBaseline(null);
      qc.invalidateQueries({ queryKey: ["user-config"] });
      setResetConfirm(false);
      showToast("success", "Reset to defaults");
    },
    onError: (err) => showToast("error", extractApiError(err), null),
  });

  async function handlePreview() {
    setPreviewLoading(true);
    setPreview(null);
    try {
      const body: Record<string, unknown> = {
        title_template: metadata.title_template,
        description_template: metadata.description_template,
      };
      appendDisplayConfigPreviewBody(body, metadata.topics_display, metadata.questions_display);
      const res = await apiClient.post<MetadataRenderPreviewData>("/templates/render-preview", body);
      setPreview(res.data);
    } catch {
      setPreview(null);
    } finally {
      setPreviewLoading(false);
    }
  }

  return (
    /* Extra bottom room so the sticky bar never covers the last control. */
    <div className={cn(dirty && "pb-24")}>
      <SectionCard
        title="Processing defaults"
        description="Applied to every new recording unless a template or a single run overrides them."
        action={
          <ActionButton size="sm" variant="secondary" onClick={() => setResetConfirm(true)} icon={<RefreshCw />}>
            Reset
          </ActionButton>
        }
      >
        <div className="grid grid-cols-1 gap-x-10 gap-y-0.5 sm:grid-cols-2">
          <Toggle
            label="Enable transcription"
            hint="ASR via AssemblyAI"
            checked={transcription.enable_transcription}
            onChange={(v) => setTranscription((c) => ({ ...c, enable_transcription: v }))}
          />
          <Toggle
            label="Extract topics"
            hint="DeepSeek topic extraction"
            checked={transcription.enable_topics}
            onChange={(v) => setTranscription((c) => ({ ...c, enable_topics: v }))}
          />
          <Toggle
            label="Generate subtitles"
            hint="Creates SRT/VTT alongside the video"
            checked={transcription.enable_subtitles}
            onChange={(v) => setTranscription((c) => ({ ...c, enable_subtitles: v }))}
          />
          <Toggle
            label="Enable trimming"
            hint="Auto-trim silence from start/end"
            checked={trimming.enable_trimming}
            onChange={(v) => setTrimming((c) => ({ ...c, enable_trimming: v }))}
          />
          <Toggle
            label="Auto-upload"
            hint="Upload immediately after processing"
            checked={upload.auto_upload}
            onChange={(v) => setUpload((c) => ({ ...c, auto_upload: v }))}
          />
          <Toggle
            label="Upload captions"
            hint="Include SRT/VTT when uploading"
            checked={upload.upload_captions}
            onChange={(v) => setUpload((c) => ({ ...c, upload_captions: v }))}
          />
        </div>

        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          <SegmentedField
            label="Transcription language"
            options={languages}
            value={transcription.language}
            onChange={(v) => setTranscription((c) => ({ ...c, language: v }))}
          />
          <SegmentedField
            label="Topic granularity"
            options={granularities}
            value={transcription.granularity}
            onChange={(v) => setTranscription((c) => ({ ...c, granularity: v }))}
          />
        </div>

        <Collapsible
          label="Advanced transcription"
          open={transcriptionAdvOpen}
          onToggle={() => setTranscriptionAdvOpen((v) => !v)}
          changed={changes.transcriptionAdv}
        >
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
            <Field label="Questions per recording" hint="Self-check questions (1–10)">
              <NumberInput
                integer
                min={1}
                max={10}
                value={transcription.questions_count}
                onCommit={(v) => setTranscription((c) => ({ ...c, questions_count: v }))}
                className="max-w-[8rem]"
              />
            </Field>
            <div className="space-y-0.5">
              <Toggle
                label="Allow transcription errors"
                hint="Continue if ASR returns partial errors"
                checked={transcription.allow_errors}
                onChange={(v) => setTranscription((c) => ({ ...c, allow_errors: v }))}
              />
              <Toggle
                label="Enable translation"
                hint="Translate transcript after ASR"
                checked={transcription.enable_translation}
                onChange={(v) => setTranscription((c) => ({ ...c, enable_translation: v }))}
              />
            </div>
          </div>

          {transcription.enable_translation && (
            <Field label="Translation language" hint="BCP-47 code, e.g. en, de, fr">
              <input
                type="text"
                value={transcription.translation_language}
                onChange={(e) => setTranscription((c) => ({ ...c, translation_language: e.target.value }))}
                placeholder="en"
                className={cn(FILTER_CONTROL, "max-w-[8rem]")}
              />
            </Field>
          )}

          <Field label="Vocabulary" hint="Key terms that improve recognition accuracy">
            <TagInput
              tags={transcription.vocabulary}
              onChange={(v) => setTranscription((c) => ({ ...c, vocabulary: v }))}
              placeholder="Add term…"
            />
          </Field>
        </Collapsible>

        <Collapsible
          label="Advanced trimming"
          open={trimmingAdvOpen}
          onToggle={() => setTrimmingAdvOpen((v) => !v)}
          changed={changes.trimmingAdv}
        >
          <Toggle
            label="Audio detection mode"
            hint="Detect audio energy rather than simple silence"
            checked={trimming.audio_detection}
            onChange={(v) => setTrimming((c) => ({ ...c, audio_detection: v }))}
          />
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Field label="Silence threshold (dB)">
              <NumberInput
                step={1}
                min={-100}
                max={0}
                value={trimming.silence_threshold}
                onCommit={(v) => setTrimming((c) => ({ ...c, silence_threshold: v }))}
              />
            </Field>
            <Field label="Min silence (s)">
              <NumberInput
                step={0.5}
                min={0}
                value={trimming.min_silence_duration}
                onCommit={(v) => setTrimming((c) => ({ ...c, min_silence_duration: v }))}
              />
            </Field>
            <Field label="Padding before (s)">
              <NumberInput
                step={0.5}
                min={0}
                value={trimming.padding_before}
                onCommit={(v) => setTrimming((c) => ({ ...c, padding_before: v }))}
              />
            </Field>
            <Field label="Padding after (s)">
              <NumberInput
                step={0.5}
                min={0}
                value={trimming.padding_after}
                onCommit={(v) => setTrimming((c) => ({ ...c, padding_after: v }))}
              />
            </Field>
          </div>
        </Collapsible>

        <Collapsible
          label="Download settings"
          open={downloadOpen}
          onToggle={() => setDownloadOpen((v) => !v)}
          changed={changes.download}
        >
          <Toggle
            label="Auto-download"
            hint="Automatically download new recordings from connected sources"
            checked={download.auto_download}
            onChange={(v) => setDownload((c) => ({ ...c, auto_download: v }))}
          />
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
            <SegmentedField
              label="Video quality"
              options={qualities}
              value={download.quality}
              onChange={(v) => setDownload((c) => ({ ...c, quality: v }))}
            />
            <Field label="Max file size (MB)">
              <NumberInput
                integer
                min={1}
                value={download.max_file_size_mb}
                onCommit={(v) => setDownload((c) => ({ ...c, max_file_size_mb: v }))}
                className="max-w-[10rem]"
              />
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Field label="Retry attempts (0–10)">
              <NumberInput
                integer
                min={0}
                max={10}
                value={download.retry_attempts}
                onCommit={(v) => setDownload((c) => ({ ...c, retry_attempts: v }))}
              />
            </Field>
            <Field label="Retry delay (s)">
              <NumberInput
                integer
                min={0}
                value={download.retry_delay}
                onCommit={(v) => setDownload((c) => ({ ...c, retry_delay: v }))}
              />
            </Field>
          </div>
        </Collapsible>

        <Collapsible
          label="Metadata defaults"
          open={metadataOpen}
          onToggle={() => setMetadataOpen((v) => !v)}
          changed={changes.metadata}
        >
          <TemplateField
            label="Title template"
            value={metadata.title_template}
            onChange={(v) => setMetadata((c) => ({ ...c, title_template: v }))}
            placeholder="{{ display_name }} | {{ topic }} ({{ date }})"
          />
          <TemplateField
            label="Description template"
            value={metadata.description_template}
            onChange={(v) => setMetadata((c) => ({ ...c, description_template: v }))}
            multiline
            placeholder={"Recording from {{ date }}\n\n{{ topics }}"}
          />
          <div className="space-y-2">
            <ActionButton
              variant="secondary"
              onClick={handlePreview}
              isPending={previewLoading}
              icon={<Eye />}
              pendingLabel="Rendering…"
            >
              Preview render
            </ActionButton>
            {preview ? <MetadataPreviewResultBox preview={preview} /> : null}
          </div>
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
            <Field label="Date format" hint="e.g. DD.MM.YYYY or YYYY-MM-DD">
              <input
                type="text"
                value={metadata.date_format}
                onChange={(e) => setMetadata((c) => ({ ...c, date_format: e.target.value }))}
                placeholder="DD.MM.YYYY"
                className={cn(FILTER_CONTROL, "max-w-[14rem] font-mono text-xs")}
              />
            </Field>
            <Field label="Default tags">
              <TagInput
                tags={metadata.tags}
                onChange={(v) => setMetadata((c) => ({ ...c, tags: v }))}
                placeholder="Add tag…"
              />
            </Field>
          </div>

          <DisplayConfigFields
            label="Show topics"
            hint="How topics appear in the description template ({{ topics }})"
            kind="topics"
            value={metadata.topics_display}
            onChange={(patch) =>
              setMetadata((c) => ({ ...c, topics_display: { ...c.topics_display, ...patch } }))
            }
          />
          <DisplayConfigFields
            label="Show questions"
            hint="How self-check questions appear in the description template ({{ questions }})"
            kind="questions"
            value={metadata.questions_display}
            onChange={(patch) =>
              setMetadata((c) => ({ ...c, questions_display: { ...c.questions_display, ...patch } }))
            }
          />
        </Collapsible>

        <Collapsible
          label="Retention"
          open={retentionOpen}
          onToggle={() => setRetentionOpen((v) => !v)}
          changed={changes.retention}
        >
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-3">
            <Field label="Soft delete (days)" hint="Move to trash after N days of inactivity">
              <NumberInput
                integer
                min={1}
                value={retention.soft_delete_days}
                onCommit={(v) => setRetention((c) => ({ ...c, soft_delete_days: v }))}
              />
            </Field>
            <Field label="Hard delete (days)" hint="Permanently delete N days after soft-delete">
              <NumberInput
                integer
                min={1}
                value={retention.hard_delete_days}
                onCommit={(v) => setRetention((c) => ({ ...c, hard_delete_days: v }))}
              />
            </Field>
            <Field label="Auto-expire (days)" hint="Archive after N days of no activity">
              <NumberInput
                integer
                min={1}
                value={retention.auto_expire_days}
                onCommit={(v) => setRetention((c) => ({ ...c, auto_expire_days: v }))}
              />
            </Field>
          </div>
        </Collapsible>

        {/* Save lives in the sticky bar below once anything is dirty; this
            inline copy keeps the action discoverable on a pristine form. */}
        {!dirty && (
          <div className="flex justify-end">
            <ActionButton
              onClick={() => updateConfig.mutate()}
              isSuccess={updateConfig.isSuccess}
              icon={<Save />}
              disabled={!baseline}
            >
              Save settings
            </ActionButton>
          </div>
        )}
      </SectionCard>

      {/* Unsaved-changes bar. Processing defaults span five collapsible
          sections, so a Save button parked at the bottom of the card is out of
          sight for most edits — and nothing else told the user the form was
          dirty. Sits above the content and inside the safe area. */}
      {dirty && (
        <div
          role="status"
          className="animate-toast-in fixed inset-x-0 bottom-0 z-40 border-t border-border bg-card/95 pb-[env(safe-area-inset-bottom)] shadow-[0_-4px_16px_-8px_rgb(0_0_0/0.2)] backdrop-blur-sm"
        >
          <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-end gap-3 px-6 py-3 sm:px-8">
            <p className="mr-auto text-sm text-secondary-foreground">
              <span className="font-semibold tabular-nums">{changes.total}</span>
              {changes.total === 1 ? " unsaved change" : " unsaved changes"}
            </p>
            <ActionButton variant="secondary" onClick={discardChanges} disabled={updateConfig.isPending}>
              Discard
            </ActionButton>
            <ActionButton
              onClick={() => updateConfig.mutate()}
              isPending={updateConfig.isPending}
              icon={<Save />}
              pendingLabel="Saving…"
            >
              Save settings
            </ActionButton>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={resetConfirm}
        title="Reset processing defaults?"
        description="Every processing setting on this page goes back to its default, including the collapsed sections. This cannot be undone."
        confirmLabel="Reset to defaults"
        confirmIcon={<RefreshCw />}
        pendingLabel="Resetting…"
        isPending={resetConfig.isPending}
        danger
        onConfirm={() => resetConfig.mutate()}
        onCancel={() => setResetConfirm(false)}
      />

      {toast && (
        <Toast
          key={toast.serial}
          type={toast.type}
          message={toast.msg}
          exiting={toast.exiting}
          onDismiss={dismissToast}
        />
      )}
    </div>
  );
}
