/** Types for GET /api/v1/references/display-config-defaults. */

export interface DisplayConfig {
  enabled: boolean;
  format: string;
  max_count: number;
  min_length: number;
  max_length: number;
  prefix: string;
  separator: string;
  show_timestamps?: boolean;
}

export interface NumericFieldBounds {
  min: number;
  max: number;
}

export interface DisplayConfigBounds {
  max_count: NumericFieldBounds;
  min_length: NumericFieldBounds;
  max_length: NumericFieldBounds;
}

export interface DisplayConfigDefaultsPayload {
  topics: DisplayConfig;
  questions: DisplayConfig;
  bounds: {
    topics: DisplayConfigBounds;
    questions: DisplayConfigBounds;
  };
}

/** React Query placeholder until /references/display-config-defaults responds. */
export const DISPLAY_CONFIG_PLACEHOLDER: DisplayConfigDefaultsPayload = {
  topics: {
    enabled: true,
    format: "numbered_list",
    max_count: 999,
    min_length: 0,
    max_length: 999,
    prefix: "",
    separator: "\n",
    show_timestamps: false,
  },
  questions: {
    enabled: false,
    format: "numbered_list",
    max_count: 20,
    min_length: 0,
    max_length: 1000,
    prefix: "",
    separator: "\n",
  },
  bounds: {
    topics: {
      max_count: { min: 1, max: 999 },
      min_length: { min: 0, max: 500 },
      max_length: { min: 10, max: 1000 },
    },
    questions: {
      max_count: { min: 1, max: 20 },
      min_length: { min: 0, max: 500 },
      max_length: { min: 10, max: 1000 },
    },
  },
};

export type DisplayConfigKind = "topics" | "questions";

export function defaultDisplayConfig(
  kind: DisplayConfigKind,
  defaults: DisplayConfigDefaultsPayload = DISPLAY_CONFIG_PLACEHOLDER,
): DisplayConfig {
  return { ...defaults[kind] };
}
