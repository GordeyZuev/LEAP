"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Image as ImageIcon, Upload, X, Check, Trash2, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/api/client";
import { FILTER_CONTROL, FILTER_LABEL } from "@/lib/filter-field-classes";
import { ActionButton } from "@/components/ui/action-button";

interface ThumbnailInfo {
  name: string;
  url: string;
  size_kb: number;
}

interface ThumbnailListResponse {
  thumbnails: ThumbnailInfo[];
}

// Module-level cache: thumbnail name → blob URL (lives for the page session)
const blobCache = new Map<string, string>();

async function fetchBlobUrl(name: string): Promise<string> {
  if (blobCache.has(name)) return blobCache.get(name)!;
  const res = await apiClient.get(`/thumbnails/${name}`, { responseType: "blob" });
  const objectUrl = URL.createObjectURL(res.data as Blob);
  blobCache.set(name, objectUrl);
  return objectUrl;
}

// ---------------------------------------------------------------------------
// ThumbnailImage — shows a single thumbnail with loader, uses name-based URL
// ---------------------------------------------------------------------------

function ThumbnailImage({ name, size }: { name: string; size?: string }) {
  const [blobUrl, setBlobUrl] = useState<string | null>(() => blobCache.get(name) ?? null);

  useEffect(() => {
    if (blobCache.has(name)) return;
    let cancelled = false;
    void fetchBlobUrl(name).then((url) => {
      if (!cancelled) setBlobUrl(url);
    });
    return () => { cancelled = true; };
  }, [name]);

  if (!blobUrl) {
    return (
      <div className="flex h-full w-full items-center justify-center rounded-lg bg-muted">
        <Loader2 size={14} className="animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={blobUrl}
      alt={name}
      title={`${name}${size ? ` (${size})` : ""}`}
      className="h-full w-full rounded-lg object-cover"
    />
  );
}

// ---------------------------------------------------------------------------
// SmallThumbPreview — tiny inline thumbnail preview (used in the trigger)
// ---------------------------------------------------------------------------

function SmallThumbPreview({ name }: { name: string }) {
  const [blobUrl, setBlobUrl] = useState<string | null>(() => blobCache.get(name) ?? null);

  useEffect(() => {
    if (blobCache.has(name)) return;
    let cancelled = false;
    void fetchBlobUrl(name).then((url) => {
      if (!cancelled) setBlobUrl(url);
    });
    return () => { cancelled = true; };
  }, [name]);

  if (!blobUrl) {
    return <div className="h-6 w-10 shrink-0 animate-pulse rounded bg-muted" />;
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={blobUrl}
      alt={name}
      className="h-6 w-10 shrink-0 rounded object-cover"
    />
  );
}

// ---------------------------------------------------------------------------
// ThumbnailPicker
// ---------------------------------------------------------------------------

interface ThumbnailPickerProps {
  value: string;
  onChange: (name: string) => void;
  label?: string;
  placeholder?: string;
}

export function ThumbnailPicker({ value, onChange, label = "Thumbnail", placeholder = "No thumbnail" }: ThumbnailPickerProps) {
  const [open, setOpen] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadName, setUploadName] = useState("");
  const [uploadError, setUploadError] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const qc = useQueryClient();

  const { data, isLoading } = useQuery<ThumbnailListResponse>({
    queryKey: ["thumbnails"],
    queryFn: async () => (await apiClient.get<ThumbnailListResponse>("/thumbnails")).data,
    enabled: open,
  });

  const upload = useMutation({
    mutationFn: async () => {
      if (!uploadFile) return;
      const form = new FormData();
      form.append("file", uploadFile);
      form.append("name", uploadName || uploadFile.name.replace(/\.[^.]+$/, ""));
      await apiClient.post("/thumbnails", form, { headers: { "Content-Type": "multipart/form-data" } });
    },
    onSuccess: () => {
      setUploadFile(null);
      setUploadName("");
      setUploadError("");
      void qc.invalidateQueries({ queryKey: ["thumbnails"] });
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setUploadError(typeof detail === "string" ? detail : "Upload failed");
    },
  });

  const deleteThumbnail = useMutation({
    mutationFn: (name: string) => apiClient.delete(`/thumbnails/${name}`),
    onSuccess: (_, name) => {
      blobCache.delete(name);
      if (value === name) onChange("");
      void qc.invalidateQueries({ queryKey: ["thumbnails"] });
    },
  });

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  function acceptFile(f: File) {
    setUploadFile(f);
    setUploadName(f.name.replace(/\.[^.]+$/, ""));
    setUploadError("");
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (f) acceptFile(f);
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
    setIsDragging(true);
  }

  function handleDragLeave(e: React.DragEvent) {
    if (!e.currentTarget.contains(e.relatedTarget as Node)) setIsDragging(false);
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setIsDragging(false);
    const f = e.dataTransfer.files[0];
    if (f && f.type.startsWith("image/")) acceptFile(f);
  }

  const thumbnails = data?.thumbnails ?? [];

  return (
    <div className="space-y-1">
      {label && <span className={FILTER_LABEL}>{label}</span>}
      <div className="flex items-center gap-2">
        {/* Trigger: shows small preview when selected */}
        <div className={cn(FILTER_CONTROL, "flex flex-1 items-center gap-2 py-1.5")}>
          {value ? (
            <>
              <SmallThumbPreview name={value} />
              <span className="flex-1 truncate text-sm text-foreground">{value}</span>
              <button
                type="button"
                onClick={() => onChange("")}
                className="shrink-0 text-muted-foreground hover:text-secondary-foreground"
              >
                <X size={14} />
              </button>
            </>
          ) : (
            <>
              <ImageIcon size={14} className="shrink-0 text-muted-foreground" />
              <span className="flex-1 truncate text-sm text-muted-foreground">{placeholder}</span>
            </>
          )}
        </div>
        <ActionButton size="sm" variant="secondary" onClick={() => setOpen(true)}>
          Select…
        </ActionButton>
      </div>

      {open && (
        <div
          ref={overlayRef}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
          onClick={(e) => { if (e.target === overlayRef.current) setOpen(false); }}
        >
          <div className="flex w-full max-w-lg flex-col rounded-2xl bg-card shadow-xl" style={{ maxHeight: "90vh" }}>
            <div className="flex items-center justify-between border-b border-border px-5 py-4">
              <h2 className="text-sm font-semibold text-foreground">Select thumbnail</h2>
              <button type="button" onClick={() => setOpen(false)} className="text-muted-foreground hover:text-secondary-foreground">
                <X size={16} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-5">
              {isLoading && (
                <div className="flex items-center justify-center py-12">
                  <Loader2 size={20} className="animate-spin text-muted-foreground" />
                </div>
              )}

              {!isLoading && thumbnails.length === 0 && (
                <p className="py-8 text-center text-sm text-muted-foreground">No thumbnails yet. Upload one below.</p>
              )}

              {!isLoading && thumbnails.length > 0 && (
                <div className="mb-5 grid grid-cols-2 sm:grid-cols-3 gap-3">
                  {thumbnails.map((t) => (
                    <div
                      key={t.name}
                      className={cn(
                        "group relative cursor-pointer rounded-xl border-2 transition-all",
                        value === t.name
                          ? "border-primary shadow-md"
                          : "border-border hover:border-primary/50"
                      )}
                      onClick={() => { onChange(t.name); setOpen(false); }}
                    >
                      <div className="aspect-video overflow-hidden rounded-[10px]">
                        <ThumbnailImage name={t.name} size={`${t.size_kb.toFixed(1)} KB`} />
                      </div>
                      <p className="truncate px-2 pb-2 pt-1 text-[10px] text-muted-foreground">{t.name}</p>
                      {value === t.name && (
                        <div className="absolute right-1.5 top-1.5 rounded-full bg-primary p-0.5 text-white">
                          <Check size={10} />
                        </div>
                      )}
                      <button
                        type="button"
                        title="Delete"
                        onClick={(e) => { e.stopPropagation(); deleteThumbnail.mutate(t.name); }}
                        disabled={deleteThumbnail.isPending}
                        className="absolute left-1.5 top-1.5 hidden rounded-full bg-white/90 p-1 text-red-500 shadow hover:bg-red-50 dark:bg-red-500/10 group-hover:flex"
                      >
                        <Trash2 size={10} />
                      </button>
                    </div>
                  ))}
                </div>
              )}

              <div className="space-y-3 rounded-xl border border-border bg-muted p-4">
                <p className="text-xs font-semibold text-secondary-foreground">Upload new thumbnail</p>
                <input
                  ref={fileRef}
                  type="file"
                  accept=".png,.jpg,.jpeg"
                  className="hidden"
                  onChange={handleFileChange}
                />
                <div
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                  onClick={() => fileRef.current?.click()}
                  className={cn(
                    "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-4 py-5 transition-colors",
                    isDragging
                      ? "border-primary bg-primary/5"
                      : uploadFile
                        ? "border-primary/40 bg-primary/5"
                        : "border-border hover:border-primary/40 hover:bg-card"
                  )}
                >
                  <Upload size={18} className={uploadFile ? "text-primary" : "text-muted-foreground"} />
                  <p className="text-center text-xs text-muted-foreground">
                    {uploadFile ? uploadFile.name : "Drag image here or click to choose"}
                  </p>
                </div>
                {uploadFile && (
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={uploadName}
                      onChange={(e) => setUploadName(e.target.value)}
                      placeholder="filename (no extension)"
                      className={cn(FILTER_CONTROL, "flex-1 text-xs")}
                      onClick={(e) => e.stopPropagation()}
                    />
                    <ActionButton
                      size="sm"
                      disabled={!uploadName}
                      isPending={upload.isPending}
                      onClick={() => upload.mutate()}
                      icon={<Upload size={12} />}
                      pendingLabel="Uploading…"
                    >
                      Upload
                    </ActionButton>
                  </div>
                )}
                {uploadError && <p className="text-xs text-red-500">{uploadError}</p>}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
