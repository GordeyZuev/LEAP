"use client";

import { NativeSelect } from "@/components/ui/native-select";
import { FILTER_CONTROL, FILTER_LABEL } from "@/lib/filter-field-classes";
import { PlatformToggle } from "@/components/platforms/platform-toggle";

// ---------------------------------------------------------------------------
// Topics / Questions display config — shared editor for the structured
// `topics_display` / `questions_display` blocks (see backend
// api/schemas/template/preset_metadata.py: TopicsDisplayConfig /
// QuestionsDisplayConfig). Reused by the Preset editor (per-platform) and the
// Template editor (common metadata level).
// ---------------------------------------------------------------------------

export interface DisplayConfig {
  enabled: boolean;
  format: string;
  max_count: number | null;
  min_length: number | null;
  max_length: number | null;
  prefix: string; // "" => omit
  separator: string;
  show_timestamps?: boolean; // topics only
}

export const DEFAULT_TOPICS_DISPLAY: DisplayConfig = {
  enabled: true,
  format: "numbered_list",
  max_count: null,
  min_length: null,
  max_length: null,
  prefix: "",
  separator: "\n",
  show_timestamps: false,
};

export const DEFAULT_QUESTIONS_DISPLAY: DisplayConfig = {
  enabled: false,
  format: "numbered_list",
  max_count: null,
  min_length: null,
  max_length: null,
  prefix: "",
  separator: "\n",
};

const FORMAT_OPTIONS = [
  { value: "numbered_list", label: "Numbered list" },
  { value: "bullet_list", label: "Bullet list" },
  { value: "dash_list", label: "Dash list" },
  { value: "comma_separated", label: "Comma separated" },
  { value: "inline", label: "Inline" },
];

// Separator stored verbatim (backend max_length 10). A small select keeps the
// common cases ergonomic while round-tripping the literal characters.
const SEPARATOR_OPTIONS = [
  { value: "\n", label: "New line" },
  { value: "\n\n", label: "Blank line" },
  { value: ", ", label: "Comma" },
  { value: " • ", label: "Bullet" },
  { value: " — ", label: "Dash" },
];

// Numeric bounds mirror the backend Field(ge=…, le=…) constraints.
type Kind = "topics" | "questions";
const COUNT_MAX: Record<Kind, number> = { topics: 999, questions: 20 };

// ---------------------------------------------------------------------------
// Serialisation helpers (exported so presets/templates round-trip identically)
// ---------------------------------------------------------------------------

/** Build the API payload, or `undefined` when the block is disabled. */
export function toDisplayPayload(value: DisplayConfig, kind: Kind): Record<string, unknown> | undefined {
  if (!value.enabled) return undefined;
  const payload: Record<string, unknown> = {
    enabled: true,
    format: value.format,
    separator: value.separator,
  };
  if (value.max_count != null) payload.max_count = value.max_count;
  if (value.min_length != null) payload.min_length = value.min_length;
  if (value.max_length != null) payload.max_length = value.max_length;
  if (value.prefix.trim()) payload.prefix = value.prefix;
  if (kind === "topics") payload.show_timestamps = !!value.show_timestamps;
  return payload;
}

/** Hydrate from an API object (or null) into editor state. */
export function fromDisplayPayload(raw: unknown, kind: Kind): DisplayConfig {
  const base = kind === "topics" ? DEFAULT_TOPICS_DISPLAY : DEFAULT_QUESTIONS_DISPLAY;
  if (!raw || typeof raw !== "object") return { ...base };
  const o = raw as Record<string, unknown>;
  const num = (v: unknown): number | null => (typeof v === "number" ? v : null);
  return {
    enabled: o.enabled != null ? Boolean(o.enabled) : true,
    format: typeof o.format === "string" ? o.format : base.format,
    max_count: num(o.max_count),
    min_length: num(o.min_length),
    max_length: num(o.max_length),
    prefix: typeof o.prefix === "string" ? o.prefix : "",
    separator: typeof o.separator === "string" ? o.separator : base.separator,
    ...(kind === "topics" ? { show_timestamps: Boolean(o.show_timestamps) } : {}),
  };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function DisplayConfigFields({
  label,
  hint,
  kind,
  value,
  onChange,
}: {
  label: string;
  hint?: string;
  kind: Kind;
  value: DisplayConfig;
  onChange: (patch: Partial<DisplayConfig>) => void;
}) {
  function numberField(
    field: "max_count" | "min_length" | "max_length",
    text: string,
    min: number,
    max: number,
  ) {
    return (
      <div className="space-y-1">
        <span className={FILTER_LABEL}>{text}</span>
        <input
          type="number"
          min={min}
          max={max}
          value={value[field] ?? ""}
          onChange={(e) => {
            const v = e.target.value;
            onChange({ [field]: v === "" ? null : Number(v) } as Partial<DisplayConfig>);
          }}
          placeholder="auto"
          className={FILTER_CONTROL}
        />
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-[#EAEAEA] bg-[#FAFAFA] px-4 py-3">
      <PlatformToggle label={label} checked={value.enabled} onChange={(v) => onChange({ enabled: v })} />
      {hint && <p className="-mt-1 mb-1 text-[11px] text-gray-400">{hint}</p>}

      {value.enabled && (
        <div className="space-y-3 border-t border-[#EAEAEA] pt-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <span className={FILTER_LABEL}>Format</span>
              <NativeSelect value={value.format} onChange={(e) => onChange({ format: e.target.value })}>
                {FORMAT_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </NativeSelect>
            </div>
            <div className="space-y-1">
              <span className={FILTER_LABEL}>Separator</span>
              <NativeSelect value={value.separator} onChange={(e) => onChange({ separator: e.target.value })}>
                {SEPARATOR_OPTIONS.map((o) => (
                  <option key={o.label} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </NativeSelect>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            {numberField("max_count", "Max count", 1, COUNT_MAX[kind])}
            {numberField("min_length", "Min length", 0, 500)}
            {numberField("max_length", "Max length", 10, 1000)}
          </div>

          <div className="space-y-1">
            <span className={FILTER_LABEL}>Prefix</span>
            <input
              type="text"
              value={value.prefix}
              onChange={(e) => onChange({ prefix: e.target.value })}
              placeholder="Optional text before the list"
              maxLength={200}
              className={FILTER_CONTROL}
            />
          </div>

          {kind === "topics" && (
            <PlatformToggle
              label="Show timestamps"
              checked={!!value.show_timestamps}
              onChange={(v) => onChange({ show_timestamps: v })}
            />
          )}
        </div>
      )}
    </div>
  );
}
