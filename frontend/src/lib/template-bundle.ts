/** Template JSON bundle v1 (export/import/edit). */

export const BUNDLE_VERSION = 1 as const;

export interface BundleReferencePreset {
  id: number;
  name: string | null;
  platform?: string | null;
  missing?: boolean;
}

export interface BundleReferenceSource {
  id: number;
  name: string | null;
  missing?: boolean;
}

export interface BundleReferencePlaylist {
  id: number;
  name: string | null;
  missing?: boolean;
}

export interface BundleReference {
  presets: BundleReferencePreset[];
  sources: BundleReferenceSource[];
  playlists: BundleReferencePlaylist[];
}

export interface TemplateBundleItem {
  id?: number;
  name: string;
  description?: string | null;
  is_draft: boolean;
  is_active: boolean;
  /** Present on export; base template must not include matching_rules in JSON edit. */
  is_default?: boolean;
  matching_rules?: Record<string, unknown> | null;
  processing_config?: Record<string, unknown> | null;
  metadata_config?: Record<string, unknown> | null;
  output_config?: Record<string, unknown> | null;
}

export interface TemplateBundle {
  leap_template_bundle: typeof BUNDLE_VERSION;
  exported_at?: string;
  reference?: BundleReference;
  templates: TemplateBundleItem[];
}

export interface TemplateImportError {
  index: number;
  name?: string | null;
  loc?: Array<string | number>;
  msg: string;
}

export interface TemplateImportWarning {
  index: number;
  code: string;
  msg: string;
}

export interface TemplateImportResult {
  ok: boolean;
  dry_run: boolean;
  created: Array<{ id: number; name: string }>;
  updated: Array<{ id: number; name: string }>;
  errors: TemplateImportError[];
  warnings: TemplateImportWarning[];
}

export interface ValidateReplaceResponse {
  ok: boolean;
  errors: string[];
  warnings: TemplateImportWarning[];
}

function isReplaceShape(obj: Record<string, unknown>): boolean {
  return (
    typeof obj.name === "string"
    && "is_draft" in obj
    && "is_active" in obj
    && !("templates" in obj)
    && !("leap_template_bundle" in obj)
  );
}

/** Parse import bundle or a single template / PUT replace document. */
export function parseBundleText(text: string): TemplateBundle {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text) as unknown;
  } catch {
    throw new Error("Invalid JSON");
  }
  if (!parsed || typeof parsed !== "object") {
    throw new Error("JSON must be an object");
  }
  const obj = parsed as Record<string, unknown>;
  if (obj.leap_template_bundle === BUNDLE_VERSION && Array.isArray(obj.templates)) {
    return obj as unknown as TemplateBundle;
  }
  if (Array.isArray(obj.templates)) {
    return { leap_template_bundle: BUNDLE_VERSION, templates: obj.templates as TemplateBundleItem[] };
  }
  if (isReplaceShape(obj)) {
    return { leap_template_bundle: BUNDLE_VERSION, templates: [obj as unknown as TemplateBundleItem] };
  }
  if (typeof obj.name === "string") {
    return { leap_template_bundle: BUNDLE_VERSION, templates: [obj as unknown as TemplateBundleItem] };
  }
  throw new Error("Unrecognized template JSON shape");
}

/** Parse Edit JSON modal text — single PUT body only (not an import bundle). */
export function parseReplaceEditorText(text: string): TemplateBundleItem {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text) as unknown;
  } catch {
    throw new Error("Invalid JSON");
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("JSON must be an object");
  }
  const obj = parsed as Record<string, unknown>;
  if ("leap_template_bundle" in obj || Array.isArray(obj.templates)) {
    throw new Error("Edit expects one template object. Use Import on the Templates list for bundles.");
  }
  if (!isReplaceShape(obj)) {
    const missing: string[] = [];
    if (typeof obj.name !== "string") missing.push("name");
    if (!("is_draft" in obj)) missing.push("is_draft");
    if (!("is_active" in obj)) missing.push("is_active");
    throw new Error(
      missing.length > 0
        ? `Missing required fields: ${missing.join(", ")}`
        : "Unrecognized template object",
    );
  }
  return obj as unknown as TemplateBundleItem;
}

export function bundleToReplaceBody(item: TemplateBundleItem): Record<string, unknown> {
  return {
    name: item.name,
    description: item.description ?? null,
    is_draft: item.is_draft,
    is_active: item.is_active,
    matching_rules: item.matching_rules ?? null,
    processing_config: item.processing_config ?? null,
    metadata_config: item.metadata_config ?? null,
    output_config: item.output_config ?? null,
  };
}

/** Editor text for PUT replace (no bundle envelope, no reference). */
export function formatReplaceEditorJson(exportData: TemplateBundle): string {
  const item = exportData.templates[0];
  if (!item) {
    throw new Error("Export has no template");
  }
  const body = bundleToReplaceBody(item);
  if (item.is_default) {
    delete body.matching_rules;
  }
  return JSON.stringify(body, null, 2);
}

export function downloadBundle(filename: string, data: TemplateBundle | object): void {
  downloadJsonText(filename, JSON.stringify(data, null, 2));
}

/** Download raw editor text (e.g. current Edit JSON buffer). */
export function downloadJsonText(filename: string, text: string): void {
  const blob = new Blob([text], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function slugifyFilename(name: string): string {
  const slug = name
    .trim()
    .toLowerCase()
    .replace(/[^\w\s-]/g, "")
    .replace(/\s+/g, "-")
    .slice(0, 60);
  return slug || "template";
}
