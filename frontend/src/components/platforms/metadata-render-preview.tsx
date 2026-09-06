"use client";

import { FormattedText } from "@/components/ui/formatted-text";
import { cn } from "@/lib/utils";

/** Response shape from `POST /templates/render-preview` and `POST /presets/render-preview`. */
export interface MetadataRenderPreviewData {
  valid: boolean;
  errors: string[];
  warnings?: string[];
  rendered_title: string | null;
  rendered_description: string | null;
  rendered_folder_path?: string | null;
  rendered_filename?: string | null;
}

export function MetadataPreviewResultBox({ preview }: { preview: MetadataRenderPreviewData }) {
  return (
    <div
      className={cn(
        "rounded-xl border p-4 text-sm",
        preview.valid ? "border-green-200 bg-green-50 dark:bg-green-500/10" : "border-red-200 bg-red-50 dark:bg-red-500/10",
      )}
    >
      {preview.errors.length > 0 && (
        <div className="mb-3 space-y-1">
          {preview.errors.map((e, i) => (
            <p key={i} className="text-xs text-red-600">
              {e}
            </p>
          ))}
        </div>
      )}
      {(preview.warnings?.length ?? 0) > 0 && (
        <div className="mb-3 space-y-1">
          {(preview.warnings ?? []).map((w, i) => (
            <p key={i} className="text-xs text-amber-700">
              {w}
            </p>
          ))}
        </div>
      )}
      {preview.rendered_title ? (
        <div className="mb-2">
          <p className="mb-1 text-xs text-muted-foreground">Title:</p>
          <p className="font-medium text-foreground">{preview.rendered_title}</p>
        </div>
      ) : null}
      {preview.rendered_description ? (
        <div
          className={cn(preview.rendered_folder_path ?? preview.rendered_filename ? "mb-2" : undefined)}
        >
          <p className="mb-1 text-xs text-muted-foreground">Description:</p>
          <FormattedText
            text={preview.rendered_description}
            className="text-xs leading-relaxed text-secondary-foreground"
          />
          <p className="mt-1.5 text-[10px] leading-snug text-muted-foreground/55">
            Public look. YouTube and VK get plain text.
          </p>
        </div>
      ) : null}
      {preview.rendered_folder_path ? (
        <div className={cn(preview.rendered_filename ? "mb-2" : undefined)}>
          <p className="mb-1 text-xs text-muted-foreground">Folder path:</p>
          <p className="font-mono text-xs text-foreground">{preview.rendered_folder_path}</p>
        </div>
      ) : null}
      {preview.rendered_filename ? (
        <div>
          <p className="mb-1 text-xs text-muted-foreground">Filename:</p>
          <p className="font-mono text-xs text-foreground">{preview.rendered_filename}</p>
        </div>
      ) : null}
    </div>
  );
}
