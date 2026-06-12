"use client";

import { NativeSelect } from "@/components/ui/native-select";
import { FILTER_CONTROL, FILTER_LABEL } from "@/lib/filter-field-classes";
import {
  defaultDisplayConfig,
  DISPLAY_CONFIG_PLACEHOLDER,
  type DisplayConfig,
  type DisplayConfigDefaultsPayload,
  type DisplayConfigKind,
} from "@/lib/display-config-defaults";
import { useDisplayConfigDefaults } from "@/hooks/use-references";
import { PlatformToggle } from "@/components/platforms/platform-toggle";

// ---------------------------------------------------------------------------
// Topics / Questions display config — shared editor for preset/template
// metadata (api/schemas/template/preset_metadata.py). Defaults from
// GET /api/v1/references/display-config-defaults via useDisplayConfigDefaults().
// ---------------------------------------------------------------------------

export type { DisplayConfig };

export function defaultTopicsDisplay(
  defaults: DisplayConfigDefaultsPayload = DISPLAY_CONFIG_PLACEHOLDER,
): DisplayConfig {
  return defaultDisplayConfig("topics", defaults);
}

export function defaultQuestionsDisplay(
  defaults: DisplayConfigDefaultsPayload = DISPLAY_CONFIG_PLACEHOLDER,
): DisplayConfig {
  return defaultDisplayConfig("questions", defaults);
}

const FORMAT_OPTIONS = [
  { value: "numbered_list", label: "Numbered list" },
  { value: "bullet_list", label: "Bullet list" },
  { value: "dash_list", label: "Dash list" },
  { value: "comma_separated", label: "Comma separated" },
  { value: "inline", label: "Inline" },
];

const SEPARATOR_OPTIONS = [
  { value: "\n", label: "New line" },
  { value: "\n\n", label: "Blank line" },
  { value: ", ", label: "Comma" },
  { value: " • ", label: "Bullet" },
  { value: " — ", label: "Dash" },
];

type Kind = DisplayConfigKind;

function resolveNumericField(
  raw: unknown,
  field: keyof Pick<DisplayConfig, "max_count" | "min_length" | "max_length">,
  kind: Kind,
  defaults: DisplayConfigDefaultsPayload,
): number {
  const fallback = defaults[kind][field];
  if (typeof raw === "number" && !Number.isNaN(raw)) return raw;
  return fallback;
}

/** Build the API payload. When disabled, sends `{ enabled: false }` so PATCH/preview can override stored config. */
export function toDisplayPayload(value: DisplayConfig, kind: Kind): Record<string, unknown> | undefined {
  if (!value.enabled) return { enabled: false };
  const payload: Record<string, unknown> = {
    enabled: true,
    format: value.format,
    separator: value.separator,
    max_count: value.max_count,
    min_length: value.min_length,
    max_length: value.max_length,
  };
  if (value.prefix.trim()) payload.prefix = value.prefix;
  if (kind === "topics") payload.show_timestamps = !!value.show_timestamps;
  return payload;
}

/** Attach topics/questions blocks to a render-preview request body. */
export function appendDisplayConfigPreviewBody(
  body: Record<string, unknown>,
  topics: DisplayConfig,
  questions: DisplayConfig,
): void {
  const td = toDisplayPayload(topics, "topics");
  if (td) body.topics_display = td;
  const qd = toDisplayPayload(questions, "questions");
  if (qd) body.questions_display = qd;
}

/** Hydrate from an API object (or null) into editor state with backend effective defaults. */
export function fromDisplayPayload(
  raw: unknown,
  kind: Kind,
  defaults: DisplayConfigDefaultsPayload = DISPLAY_CONFIG_PLACEHOLDER,
): DisplayConfig {
  const base = defaultDisplayConfig(kind, defaults);
  if (!raw || typeof raw !== "object") return { ...base };
  const o = raw as Record<string, unknown>;
  return {
    enabled: o.enabled != null ? Boolean(o.enabled) : base.enabled,
    format: typeof o.format === "string" ? o.format : base.format,
    max_count: resolveNumericField(o.max_count, "max_count", kind, defaults),
    min_length: resolveNumericField(o.min_length, "min_length", kind, defaults),
    max_length: resolveNumericField(o.max_length, "max_length", kind, defaults),
    prefix: typeof o.prefix === "string" ? o.prefix : base.prefix,
    separator: typeof o.separator === "string" ? o.separator : base.separator,
    ...(kind === "topics"
      ? {
          show_timestamps:
            o.show_timestamps != null
              ? Boolean(o.show_timestamps)
              : o.include_timestamps != null
                ? Boolean(o.include_timestamps)
                : !!base.show_timestamps,
        }
      : {}),
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
  const { data: defaults = DISPLAY_CONFIG_PLACEHOLDER } = useDisplayConfigDefaults();
  const bounds = defaults.bounds[kind];

  function numberField(
    field: "max_count" | "min_length" | "max_length",
    text: string,
  ) {
    const { min, max } = bounds[field];
    const fallback = defaults[kind][field];
    return (
      <div className="space-y-1">
        <span className={FILTER_LABEL}>{text}</span>
        <input
          type="number"
          min={min}
          max={max}
          value={value[field]}
          onChange={(e) => {
            const v = e.target.value;
            const parsed = v === "" ? fallback : Number(v);
            onChange({ [field]: Number.isNaN(parsed) ? fallback : parsed } as Partial<DisplayConfig>);
          }}
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
            {numberField("max_count", "Max count")}
            {numberField("min_length", "Min length")}
            {numberField("max_length", "Max length")}
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
