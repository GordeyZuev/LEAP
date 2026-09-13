"use client";

import Link from "next/link";
import { useEffect, useId, useState } from "react";
import { Download, AlignLeft } from "lucide-react";
import { Modal } from "@/components/ui/modal";
import { ActionButton } from "@/components/ui/action-button";
import { Field } from "@/components/ui/field";
import { Toggle } from "@/components/ui/toggle";
import { apiClient } from "@/api/client";
import {
  type TemplateImportResult,
  type ValidateReplaceResponse,
  parseBundleText,
  parseReplaceEditorText,
  bundleToReplaceBody,
  downloadJsonText,
} from "@/lib/template-bundle";

export type TemplateJsonModalMode = "import" | "edit";

export interface TemplateJsonModalProps {
  open: boolean;
  onClose: () => void;
  mode: TemplateJsonModalMode;
  initialText?: string;
  templateId?: number;
  /** Base name for Download this in edit mode (without extension). */
  downloadBasename?: string;
  onImportSuccess?: (result: TemplateImportResult) => void;
  onReplaceSuccess?: () => void;
}

const JSON_INPUT =
  "w-full min-h-[min(60vh,520px)] resize-y rounded-xl border border-border bg-muted/30 px-3 py-2.5 font-mono text-xs leading-relaxed text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/10";

function formatJsonText(raw: string): string {
  return JSON.stringify(JSON.parse(raw), null, 2);
}

function apiErrorMessage(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((entry) => {
        if (entry && typeof entry === "object" && "msg" in entry) {
          const loc = "loc" in entry && Array.isArray(entry.loc) ? entry.loc.join(".") : "";
          return loc ? `${loc}: ${String((entry as { msg: string }).msg)}` : String((entry as { msg: string }).msg);
        }
        return JSON.stringify(entry);
      })
      .join("; ");
  }
  if (detail && typeof detail === "object") return JSON.stringify(detail);
  if (err instanceof Error) return err.message;
  return fallback;
}

function clearValidation(setters: {
  setImportResult: (v: TemplateImportResult | null) => void;
  setReplaceResult: (v: ValidateReplaceResponse | null) => void;
  setError: (v: string | null) => void;
}) {
  setters.setImportResult(null);
  setters.setReplaceResult(null);
  setters.setError(null);
}

export function TemplateJsonModal({
  open,
  onClose,
  mode,
  initialText = "",
  templateId,
  downloadBasename = "template",
  onImportSuccess,
  onReplaceSuccess,
}: TemplateJsonModalProps) {
  const titleId = useId();
  const [text, setText] = useState(initialText);
  const [importResult, setImportResult] = useState<TemplateImportResult | null>(null);
  const [replaceResult, setReplaceResult] = useState<ValidateReplaceResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [autoRematch, setAutoRematch] = useState(false);

  /* eslint-disable react-hooks/set-state-in-effect -- reset when dialog opens */
  useEffect(() => {
    if (open) {
      setText(initialText);
      setImportResult(null);
      setReplaceResult(null);
      setError(null);
      setAutoRematch(false);
    }
  }, [open, initialText]);

  const title = mode === "edit" ? "Edit JSON config" : "Import JSON config";
  const docsHref = "/docs#templates-json-config";

  function handleDownloadThis() {
    downloadJsonText(`${downloadBasename}-config.json`, text);
  }

  function handleFormatJson() {
    setError(null);
    try {
      setText(formatJsonText(text));
    } catch {
      setError("Invalid JSON — fix syntax before formatting");
    }
  }

  async function handleValidate() {
    setError(null);
    setImportResult(null);
    setReplaceResult(null);
    setPending(true);
    try {
      if (mode === "edit") {
        if (templateId == null) {
          throw new Error("Template id is required");
        }
        const item = parseReplaceEditorText(text);
        const res = await apiClient.post<ValidateReplaceResponse>(
          `/templates/${templateId}/validate-replace`,
          bundleToReplaceBody(item),
        );
        setReplaceResult(res.data);
        if (!res.data.ok) {
          setError("Fix validation errors below");
        }
      } else {
        const bundle = parseBundleText(text);
        const res = await apiClient.post<TemplateImportResult>("/templates/import?dry_run=true", bundle);
        setImportResult(res.data);
        if (!res.data.ok) {
          setError("Fix validation errors below");
        }
      }
    } catch (err: unknown) {
      setError(apiErrorMessage(err, "Validation failed"));
    } finally {
      setPending(false);
    }
  }

  async function handleSave() {
    setError(null);
    setPending(true);
    try {
      if (mode === "edit") {
        if (templateId == null) {
          throw new Error("Template id is required");
        }
        const item = parseReplaceEditorText(text);
        await apiClient.put(`/templates/${templateId}`, bundleToReplaceBody(item));
        onReplaceSuccess?.();
        onClose();
      } else {
        const bundle = parseBundleText(text);
        const res = await apiClient.post<TemplateImportResult>(
          `/templates/import?dry_run=false&auto_rematch=${autoRematch ? "true" : "false"}`,
          bundle,
        );
        if (!res.data.ok) {
          setImportResult(res.data);
          setError("Import failed — fix errors below");
          return;
        }
        onImportSuccess?.(res.data);
        onClose();
      }
    } catch (err: unknown) {
      setError(apiErrorMessage(err, mode === "edit" ? "Save failed" : "Import failed"));
    } finally {
      setPending(false);
    }
  }

  function handleTextChange(value: string) {
    setText(value);
    if (importResult || replaceResult || error) {
      clearValidation({ setImportResult, setReplaceResult, setError });
    }
  }

  const validateOk = mode === "edit" ? replaceResult?.ok : importResult?.ok;
  const warnings = mode === "edit" ? replaceResult?.warnings : importResult?.warnings;
  const errors =
    mode === "edit"
      ? (replaceResult?.errors ?? [])
      : (importResult?.errors?.map((e) => e.msg) ?? []);

  return (
    <Modal
      open={open}
      onClose={onClose}
      labelledBy={titleId}
      panelClassName={mode === "edit" ? "max-w-3xl" : "max-w-2xl"}
    >
      <div className="space-y-4 p-6">
        <div className="space-y-2">
          <h2 id={titleId} className="text-base font-semibold text-foreground">
            {title}
          </h2>
          {mode === "edit" ? (
            <ul className="list-none space-y-1.5 text-sm leading-snug text-muted-foreground">
              <li>Full replace — same validation as the form.</li>
              <li>
                <Link href={docsHref} className="font-medium text-primary underline-offset-2 hover:underline">
                  Documentation
                </Link>
              </li>
            </ul>
          ) : (
            <ul className="list-none space-y-1.5 text-sm leading-snug text-muted-foreground">
              <li>Paste a bundle or one template object.</li>
              <li>Validate, then Import.</li>
              <li>
                <Link href={docsHref} className="font-medium text-primary underline-offset-2 hover:underline">
                  Documentation
                </Link>
              </li>
            </ul>
          )}
        </div>

        <div className="flex flex-wrap gap-2">
          {mode === "edit" && (
            <ActionButton
              type="button"
              size="sm"
              variant="secondary"
              icon={<Download size={14} />}
              onClick={handleDownloadThis}
              disabled={pending || !text.trim()}
            >
              Download this
            </ActionButton>
          )}
          <ActionButton
            type="button"
            size="sm"
            variant="secondary"
            icon={<AlignLeft size={14} />}
            onClick={handleFormatJson}
            disabled={pending || !text.trim()}
          >
            Format JSON
          </ActionButton>
        </div>

        <Field label="Configuration">
          <textarea
            className={JSON_INPUT}
            value={text}
            onChange={(e) => handleTextChange(e.target.value)}
            spellCheck={false}
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="off"
          />
        </Field>

        {mode === "import" && (
          <Toggle
            label="Rematch unmapped recordings after import"
            checked={autoRematch}
            onChange={setAutoRematch}
          />
        )}

        {error && <p className="text-sm text-destructive">{error}</p>}
        {validateOk === false && errors.length > 0 && (
          <ul className="max-h-32 list-disc overflow-y-auto pl-5 text-sm text-destructive">
            {errors.map((msg, i) => (
              <li key={`${i}-${msg}`}>{msg}</li>
            ))}
          </ul>
        )}
        {validateOk === true && (
          <p className="text-sm text-muted-foreground">
            {mode === "import"
              ? `Ready: ${importResult?.created.length ?? 0} create, ${importResult?.updated.length ?? 0} update`
              : "Configuration is valid."}
          </p>
        )}
        {warnings && warnings.length > 0 && (
          <ul className="max-h-24 list-disc overflow-y-auto pl-5 text-xs text-muted-foreground">
            {warnings.map((w) => (
              <li key={`${w.index}-${w.code}`}>{w.msg}</li>
            ))}
          </ul>
        )}

        <div className="flex flex-wrap justify-end gap-2 border-t border-border pt-4">
          <ActionButton variant="secondary" onClick={onClose} disabled={pending}>
            Cancel
          </ActionButton>
          <ActionButton variant="secondary" onClick={handleValidate} isPending={pending} pendingLabel="Checking…">
            Validate
          </ActionButton>
          <ActionButton onClick={handleSave} isPending={pending} pendingLabel="Saving…">
            {mode === "edit" ? "Save" : "Import"}
          </ActionButton>
        </div>
      </div>
    </Modal>
  );
}
