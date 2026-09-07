"use client";

import { useEffect, useId, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Image as ImageIcon, Upload, X, Check, Trash2, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/api/client";
import { FILTER_CONTROL, FILTER_LABEL } from "@/lib/filter-field-classes";
import { ActionButton } from "@/components/ui/action-button";
import { Modal } from "@/components/ui/modal";

interface ThumbnailInfo {
  name: string;
  url: string;
  size_kb: number;
}

interface ThumbnailListResponse {
  thumbnails: ThumbnailInfo[];
}

const blobCache = new Map<string, string>();

async function fetchBlobUrl(name: string): Promise<string> {
  if (blobCache.has(name)) return blobCache.get(name)!;
  const res = await apiClient.get(`/thumbnails/${name}`, { responseType: "blob" });
  const objectUrl = URL.createObjectURL(res.data as Blob);
  blobCache.set(name, objectUrl);
  return objectUrl;
}

function ThumbnailImage({ name, size }: { name: string; size?: string }) {
  const [blobUrl, setBlobUrl] = useState<string | null>(() => blobCache.get(name) ?? null);

  useEffect(() => {
    if (blobCache.has(name)) return;
    let cancelled = false;
    void fetchBlobUrl(name).then((url) => {
      if (!cancelled) setBlobUrl(url);
    });
    return () => {
      cancelled = true;
    };
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

function SmallThumbPreview({ name }: { name: string }) {
  const [blobUrl, setBlobUrl] = useState<string | null>(() => blobCache.get(name) ?? null);

  useEffect(() => {
    if (blobCache.has(name)) return;
    let cancelled = false;
    void fetchBlobUrl(name).then((url) => {
      if (!cancelled) setBlobUrl(url);
    });
    return () => {
      cancelled = true;
    };
  }, [name]);

  if (!blobUrl) {
    return <div className="h-8 w-12 shrink-0 animate-pulse rounded-md bg-muted" />;
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={blobUrl} alt="" className="h-8 w-12 shrink-0 rounded-md object-cover" />
  );
}

interface ThumbnailPickerProps {
  value: string;
  onChange: (name: string) => void;
  label?: string;
  placeholder?: string;
}

export function ThumbnailPicker({
  value,
  onChange,
  label = "Thumbnail",
  placeholder = "No thumbnail",
}: ThumbnailPickerProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadName, setUploadName] = useState("");
  const [uploadError, setUploadError] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const titleId = useId();
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

  function close() {
    setOpen(false);
    setQuery("");
  }

  const thumbnails = data?.thumbnails ?? [];
  const needle = query.trim().toLowerCase();
  const filtered = needle
    ? thumbnails.filter((t) => t.name.toLowerCase().includes(needle))
    : thumbnails;

  return (
    <div className="space-y-1">
      {label && <span className={FILTER_LABEL}>{label}</span>}
      <div
        className={cn(FILTER_CONTROL, "flex h-auto min-h-[2.875rem] cursor-pointer items-center gap-2 p-2")}
        onClick={() => setOpen(true)}
      >
        <button
          type="button"
          aria-label={label}
          aria-haspopup="dialog"
          aria-expanded={open}
          onClick={() => setOpen(true)}
          className="flex min-w-0 flex-1 cursor-pointer items-center gap-2 text-left font-medium"
        >
          {value ? (
            <>
              <SmallThumbPreview name={value} />
              <span className="min-w-0 flex-1 truncate">{value}</span>
            </>
          ) : (
            <>
              <ImageIcon size={16} strokeWidth={2} className="shrink-0 text-muted-foreground" />
              <span className="min-w-0 flex-1 truncate text-muted-foreground">{placeholder}</span>
            </>
          )}
          <span className="inline-flex h-8 shrink-0 items-center rounded-lg bg-muted px-2.5 text-sm font-medium text-secondary-foreground">
            Select
          </span>
        </button>
        {value ? (
          <button
            type="button"
            aria-label="Clear image"
            onClick={(e) => {
              e.stopPropagation();
              onChange("");
            }}
            className="flex h-8 w-8 shrink-0 items-center justify-center text-muted-foreground hover:text-secondary-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
          >
            <X size={16} />
          </button>
        ) : null}
      </div>

      <Modal open={open} onClose={close} labelledBy={titleId} panelClassName="max-w-lg">
        <div className="flex h-[min(90vh,40rem)] flex-col overflow-hidden">
          <div className="flex items-center justify-between border-b border-border px-5 py-4">
            <h2 id={titleId} className="text-sm font-semibold text-foreground">
              Select image
            </h2>
            <button
              type="button"
              onClick={close}
              aria-label="Close dialog"
              tabIndex={-1}
              className="flex min-h-11 min-w-11 items-center justify-center text-muted-foreground hover:text-secondary-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
            >
              <X size={16} />
            </button>
          </div>

          <div className="border-b border-border px-5 py-3">
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search images"
              aria-label="Search images"
              className={FILTER_CONTROL}
            />
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto p-5">
            {isLoading && (
              <div className="flex items-center justify-center py-12">
                <Loader2 size={20} className="animate-spin text-muted-foreground" />
              </div>
            )}

            {!isLoading && thumbnails.length === 0 && (
              <p className="py-8 text-center text-sm text-muted-foreground">No images yet. Upload one below.</p>
            )}

            {!isLoading && thumbnails.length > 0 && filtered.length === 0 && (
              <p className="py-8 text-center text-sm text-muted-foreground">Nothing matches</p>
            )}

            {!isLoading && filtered.length > 0 && (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                {filtered.map((t) => (
                  <div
                    key={t.name}
                    className={cn(
                      "group relative cursor-pointer rounded-xl border-2 transition-colors",
                      value === t.name ? "border-primary" : "border-border hover:border-primary/50",
                    )}
                    onClick={() => {
                      onChange(t.name);
                      close();
                    }}
                  >
                    <div className="aspect-video overflow-hidden rounded-[10px]">
                      <ThumbnailImage name={t.name} size={`${t.size_kb.toFixed(1)} KB`} />
                    </div>
                    <p className="truncate px-2 pb-2 pt-1 text-xs text-muted-foreground">{t.name}</p>
                    {value === t.name && (
                      <div className="absolute right-1.5 top-1.5 rounded-full bg-primary p-0.5 text-white">
                        <Check size={10} />
                      </div>
                    )}
                    <button
                      type="button"
                      title="Delete"
                      onClick={(e) => {
                        e.stopPropagation();
                        deleteThumbnail.mutate(t.name);
                      }}
                      disabled={deleteThumbnail.isPending}
                      className="absolute left-1.5 top-1.5 hidden rounded-full bg-white/90 p-1 text-red-500 shadow hover:bg-red-50 group-hover:flex dark:hover:bg-red-500/10"
                    >
                      <Trash2 size={10} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="space-y-3 border-t border-border px-5 py-4">
            <p className="text-xs font-semibold text-secondary-foreground">Upload new image</p>
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
                    : "border-border hover:border-primary/40 hover:bg-card",
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
      </Modal>
    </div>
  );
}
