"use client";

import { Toggle } from "@/components/ui/toggle";
import { AdvancedBlock } from "@/components/ui/disclosure";
import { Field } from "@/components/ui/field";
import { NativeSelect } from "@/components/ui/native-select";
import { NumberInput } from "@/components/ui/number-input";
import { TagInput } from "@/components/ui/tag-input";
import { FILTER_CONTROL, FILTER_LABEL } from "@/lib/filter-field-classes";

export interface TrimmingForm {
  enable_trimming: boolean;
  silence_threshold: number;
  min_silence_duration: number;
  padding_before: number;
  padding_after: number;
}

export const DEFAULT_TRIMMING: TrimmingForm = {
  enable_trimming: true,
  silence_threshold: -40,
  min_silence_duration: 2,
  padding_before: 5,
  padding_after: 5,
};

export interface ProcessingFormFields {
  enable_transcription: boolean;
  enable_topics: boolean;
  enable_subtitles: boolean;
  language: string;
  granularity: string;
  questions_count: number;
  allow_errors: boolean;
  vocabulary: string[];
  prompt: string;
  trimming: TrimmingForm;
}

export function trimmingFromApi(raw: unknown): TrimmingForm {
  const o = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  return {
    enable_trimming: o.enable_trimming != null ? Boolean(o.enable_trimming) : DEFAULT_TRIMMING.enable_trimming,
    silence_threshold: typeof o.silence_threshold === "number" ? o.silence_threshold : DEFAULT_TRIMMING.silence_threshold,
    min_silence_duration:
      typeof o.min_silence_duration === "number" ? o.min_silence_duration : DEFAULT_TRIMMING.min_silence_duration,
    padding_before: typeof o.padding_before === "number" ? o.padding_before : DEFAULT_TRIMMING.padding_before,
    padding_after: typeof o.padding_after === "number" ? o.padding_after : DEFAULT_TRIMMING.padding_after,
  };
}

export function ProcessingFields({
  value,
  onChange,
  languages,
  granularities,
}: {
  value: ProcessingFormFields;
  onChange: (patch: Partial<ProcessingFormFields>) => void;
  languages: { value: string; label: string }[];
  granularities: { value: string; label: string }[];
}) {
  const t = value.trimming;
  function setTrim(patch: Partial<TrimmingForm>) {
    onChange({ trimming: { ...t, ...patch } });
  }

  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <Toggle
          label="Enable transcription"
          checked={value.enable_transcription}
          onChange={(v) => onChange({ enable_transcription: v })}
        />
        <Toggle
          label="Extract topics"
          checked={value.enable_topics}
          onChange={(v) => onChange({ enable_topics: v })}
        />
        <Toggle
          label="Generate subtitles"
          checked={value.enable_subtitles}
          onChange={(v) => onChange({ enable_subtitles: v })}
        />
      </div>

      <Field label="Language">
        <NativeSelect value={value.language} onChange={(e) => onChange({ language: e.target.value })}>
          {languages.map((l) => (
            <option key={l.value} value={l.value}>
              {l.label}
            </option>
          ))}
        </NativeSelect>
      </Field>
      {value.enable_topics ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Topic granularity">
            <NativeSelect value={value.granularity} onChange={(e) => onChange({ granularity: e.target.value })}>
              {granularities.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field label="Questions count">
            <NumberInput
              integer
              min={1}
              max={10}
              value={value.questions_count}
              onCommit={(n) => onChange({ questions_count: n })}
            />
          </Field>
        </div>
      ) : null}

      <AdvancedBlock title="Extra processing settings">
        <Toggle
          label="Trim silence"
          hint="Remove leading and trailing quiet from the video"
          checked={t.enable_trimming}
          onChange={(v) => setTrim({ enable_trimming: v })}
        />
        {t.enable_trimming ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <span className={FILTER_LABEL}>Silence threshold (dB)</span>
              <input
                type="number"
                max={0}
                min={-100}
                step={1}
                value={t.silence_threshold}
                onChange={(e) => setTrim({ silence_threshold: Number(e.target.value) || -40 })}
                className={FILTER_CONTROL}
              />
            </div>
            <div className="space-y-1">
              <span className={FILTER_LABEL}>Min silence (seconds)</span>
              <input
                type="number"
                min={0}
                step={0.5}
                value={t.min_silence_duration}
                onChange={(e) => setTrim({ min_silence_duration: Number(e.target.value) || 0 })}
                className={FILTER_CONTROL}
              />
            </div>
            <div className="space-y-1">
              <span className={FILTER_LABEL}>Padding before (seconds)</span>
              <input
                type="number"
                min={0}
                step={0.5}
                value={t.padding_before}
                onChange={(e) => setTrim({ padding_before: Number(e.target.value) || 0 })}
                className={FILTER_CONTROL}
              />
            </div>
            <div className="space-y-1">
              <span className={FILTER_LABEL}>Padding after (seconds)</span>
              <input
                type="number"
                min={0}
                step={0.5}
                value={t.padding_after}
                onChange={(e) => setTrim({ padding_after: Number(e.target.value) || 0 })}
                className={FILTER_CONTROL}
              />
            </div>
          </div>
        ) : null}
        <Toggle
          label="Allow transcription errors"
          hint="Continue the pipeline if ASR returns partial errors"
          checked={value.allow_errors}
          onChange={(v) => onChange({ allow_errors: v })}
        />
        <Field label="ASR prompt">
          <textarea
            value={value.prompt}
            onChange={(e) => onChange({ prompt: e.target.value })}
            rows={3}
            className={FILTER_CONTROL}
            placeholder="Optional hint for the transcriber"
          />
        </Field>
        <Field label="Vocabulary">
          <TagInput tags={value.vocabulary} onChange={(vocabulary) => onChange({ vocabulary })} placeholder="Add term…" />
        </Field>
      </AdvancedBlock>
    </div>
  );
}
