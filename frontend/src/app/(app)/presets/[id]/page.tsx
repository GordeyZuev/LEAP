"use client";

import { use, useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { ArrowLeft, Save, Copy, Trash2, Eye } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/api/client";
import { Toast } from "@/components/ui/toast";
import { ActionButton } from "@/components/ui/action-button";
import { useToast } from "@/hooks/use-toast";
import {
  YouTubeFields,
  VkFields,
  YandexDiskFields,
  type YouTubeFieldsValue,
  type VkFieldsValue,
  type YandexDiskFieldsValue,
  DEFAULT_YOUTUBE_FIELDS,
  DEFAULT_VK_FIELDS,
  DEFAULT_YANDEX_DISK_FIELDS,
  youtubeFieldsFromApi,
  vkFieldsFromApi,
  yandexFieldsFromApi,
  youtubeFieldsToApi,
  vkFieldsToApi,
  yandexFieldsToApi,
  LeapLookFields,
  DEFAULT_LEAP_FIELDS,
  leapFieldsFromApi,
  type LeapFieldsValue,
} from "@/components/platforms/platform-fields";
import { appendDisplayConfigPreviewBody } from "@/components/platforms/display-config-fields";
import { FILTER_CONTROL } from "@/lib/filter-field-classes";
import { NativeSelect } from "@/components/ui/native-select";
import { Field } from "@/components/ui/field";
import { CreatePlaceholder } from "@/components/ui/create-placeholder";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Toggle } from "@/components/ui/toggle";
import {
  MetadataPreviewResultBox,
  type MetadataRenderPreviewData,
} from "@/components/platforms/metadata-render-preview";

type Platform = "youtube" | "vk" | "yandex_disk" | "leap";

type PlatformOption = { value: Platform; label: string; featured?: boolean };

const BASE_PLATFORMS: PlatformOption[] = [
  { value: "leap", label: "LEAP", featured: true },
  { value: "youtube", label: "YouTube" },
  { value: "yandex_disk", label: "Yandex Disk" },
];

function editorPlatforms(current: Platform): PlatformOption[] {
  if (current === "vk") {
    return [{ value: "vk", label: "VK Video" }, ...BASE_PLATFORMS];
  }
  return BASE_PLATFORMS;
}

const PLATFORM_CHIP_LABEL: Record<Platform, string> = {
  leap: "LEAP",
  youtube: "YouTube",
  vk: "VK Video",
  yandex_disk: "Yandex Disk",
};

interface CredentialItem {
  id: number;
  platform: string;
  account_name: string | null;
}

// ---------------------------------------------------------------------------
// Per-platform meta helpers
// ---------------------------------------------------------------------------

type PlatformMeta = YouTubeFieldsValue | VkFieldsValue | YandexDiskFieldsValue | LeapFieldsValue;

function getDefaultMeta(platform: Platform): PlatformMeta {
  if (platform === "youtube")     return { ...DEFAULT_YOUTUBE_FIELDS };
  if (platform === "vk")          return { ...DEFAULT_VK_FIELDS };
  if (platform === "leap")        return { ...DEFAULT_LEAP_FIELDS };
  return { ...DEFAULT_YANDEX_DISK_FIELDS };
}

function coerceMeta(platform: Platform, raw: unknown): PlatformMeta {
  if (platform === "youtube") return youtubeFieldsFromApi(raw);
  if (platform === "vk") return vkFieldsFromApi(raw);
  if (platform === "leap") return leapFieldsFromApi(raw);
  return yandexFieldsFromApi(raw);
}

// ---------------------------------------------------------------------------
// Serialise meta back to API format (presets include per-platform display
// config and the full Yandex extended fields).
// ---------------------------------------------------------------------------

function serialiseMeta(platform: Platform, meta: PlatformMeta): Record<string, unknown> {
  if (platform === "youtube") return youtubeFieldsToApi(meta as YouTubeFieldsValue, { includeDisplay: true });
  if (platform === "vk") return vkFieldsToApi(meta as VkFieldsValue, { includeDisplay: true });
  if (platform === "leap") {
    const m = meta as LeapFieldsValue;
    return {
      title_template: m.title_template || undefined,
      description_template: m.description_template || undefined,
      thumbnail_name: m.thumbnail_name || undefined,
      playlist_ids: m.playlist_ids,
      auto_share: Boolean(m.auto_share),
    };
  }
  return yandexFieldsToApi(meta as YandexDiskFieldsValue, { includeExtended: true });
}

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

export default function PresetEditorPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const isNew = id === "new";
  const router = useRouter();
  const qc = useQueryClient();

  const [name,        setName]        = useState("");
  const [description, setDescription] = useState("");
  const [platform,    setPlatform]    = useState<Platform>("leap");
  const [credId,      setCredId]      = useState<number | "">("");
  const [isActive,    setIsActive]    = useState(true);
  const [meta,        setMeta]        = useState<PlatformMeta>({ ...DEFAULT_LEAP_FIELDS });
  const { toast, show: showToast, dismiss: dismissToast } = useToast();

  const [savedSnapshot, setSavedSnapshot] = useState(
    () => JSON.stringify({ name: "", description: "", credId: "", isActive: true, meta: { ...DEFAULT_LEAP_FIELDS } }),
  );
  const [confirmCopy, setConfirmCopy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmLeave, setConfirmLeave] = useState(false);
  const [pendingHref, setPendingHref] = useState("");

  const [renderPreview, setRenderPreview] = useState<MetadataRenderPreviewData | null>(null);
  const [renderPreviewLoading, setRenderPreviewLoading] = useState(false);

  const { data: existing } = useQuery({
    queryKey: ["preset", id],
    queryFn: async () => (await apiClient.get(`/presets/${id}`)).data,
    enabled: !isNew,
  });

  const { data: credsData } = useQuery<{ items: CredentialItem[] }>({
    queryKey: ["credentials-list"],
    queryFn: async () => (await apiClient.get("/credentials?per_page=50")).data,
  });

  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (!existing) return;
    const raw = existing.platform ?? "youtube";
    const p = (raw === "vk_video" ? "vk" : raw) as Platform;
    const newName = existing.name ?? "";
    const newDesc = existing.description ?? "";
    const newCredId = existing.credential_id ?? "";
    const newActive = existing.is_active ?? true;
    const newMeta = coerceMeta(p, existing.preset_metadata);
    setPlatform(p);
    setName(newName);
    setDescription(newDesc);
    setCredId(newCredId);
    setIsActive(newActive);
    setMeta(newMeta);
    setSavedSnapshot(JSON.stringify({ name: newName, description: newDesc, credId: newCredId, isActive: newActive, meta: newMeta }));
  }, [existing]);
  /* eslint-enable react-hooks/set-state-in-effect */

  const save = useMutation({
    mutationFn: async () => {
      const body: Record<string, unknown> = {
        name,
        description: description || undefined,
        platform,
        is_active: isActive,
        preset_metadata: serialiseMeta(platform, meta),
      };
      if (platform !== "leap") {
        body.credential_id = credId || undefined;
      }
      if (isNew) {
        return (await apiClient.post("/presets", body)).data;
      } else {
        return (await apiClient.patch(`/presets/${id}`, body)).data;
      }
    },
    onSuccess: (result) => {
      setSavedSnapshot(JSON.stringify({ name, description, credId, isActive, meta }));
      qc.invalidateQueries({ queryKey: ["presets"] });
      showToast("success", "Preset saved");
      if (isNew) router.push(`/presets/${result.id}`);
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      showToast("error", typeof detail === "string" ? detail : "Failed to save preset");
    },
  });

  const copyPreset = useMutation({
    mutationFn: () =>
      apiClient.post<{ id: number }>(`/presets/${id}/copy`).then((r) => r.data),
    onSuccess: (result) => router.push(`/presets/${result.id}`),
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      showToast("error", typeof detail === "string" ? detail : "Failed to copy preset");
    },
  });

  const deletePreset = useMutation({
    mutationFn: () => apiClient.delete(`/presets/${id}`),
    onSuccess: () => router.push("/presets"),
    onError: () => showToast("error", "Failed to delete preset"),
  });

  function changePlatform(p: Platform) {
    setPlatform(p);
    setMeta(getDefaultMeta(p));
    setCredId("");
  }

  function patchMeta(patch: Partial<PlatformMeta>) {
    setMeta((prev) => ({ ...prev, ...patch } as PlatformMeta));
  }

  async function handleRenderPreview() {
    setRenderPreviewLoading(true);
    setRenderPreview(null);
    try {
      const body: Record<string, unknown> = {};
      if (platform === "youtube" || platform === "vk" || platform === "leap") {
        const m = meta as YouTubeFieldsValue | VkFieldsValue | LeapFieldsValue;
        if (m.title_template.trim()) body.title_template = m.title_template;
        if (m.description_template.trim()) body.description_template = m.description_template;
        if (platform !== "leap") {
          appendDisplayConfigPreviewBody(body, (m as YouTubeFieldsValue | VkFieldsValue).topics_display, (m as YouTubeFieldsValue | VkFieldsValue).questions_display);
        }
      } else {
        const yd = meta as YandexDiskFieldsValue;
        if (yd.folder_path_template?.trim()) body.folder_path_template = yd.folder_path_template;
        if (yd.filename_template?.trim()) body.filename_template = yd.filename_template;
      }
      const res = await apiClient.post<MetadataRenderPreviewData>("/presets/render-preview", body);
      setRenderPreview(res.data);
    } catch {
      setRenderPreview(null);
    } finally {
      setRenderPreviewLoading(false);
    }
  }

  const creds = (credsData?.items ?? []).filter((c) => {
    if (platform === "youtube")     return c.platform === "youtube";
    if (platform === "vk")          return c.platform === "vk_video";
    if (platform === "yandex_disk") return c.platform === "yandex_disk";
    return false;
  });

  const isDirty =
    JSON.stringify({ name, description, credId, isActive, meta }) !== savedSnapshot;

  const statusLabel = isActive ? "Active" : "Inactive";
  const statusColor = isActive
    ? "bg-green-100 text-green-700 dark:bg-green-500/15 dark:text-green-300"
    : "bg-muted text-muted-foreground";

  const platformChoices = editorPlatforms(platform);

  return (
    <div className="w-full min-w-0 p-6 sm:p-8">
      {/* Header */}
      <div className="mb-6 flex flex-wrap items-center gap-4">
        <button
          type="button"
          onClick={() => {
            if (isDirty) { setPendingHref("/presets"); setConfirmLeave(true); }
            else router.push("/presets");
          }}
          className="flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-secondary-foreground"
        >
          <ArrowLeft size={16} /> Presets
        </button>
        <span className="text-gray-300">/</span>
        <h1 className="flex-1 text-lg font-semibold text-foreground">
          {isNew ? "New preset" : (existing?.name ?? "…")}
        </h1>
        <span
          className={cn(
            "rounded-full px-2.5 py-1 text-[11px] font-medium",
            platform === "leap" ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground",
          )}
        >
          {PLATFORM_CHIP_LABEL[platform]}
        </span>
        {!isNew && (
          <ActionButton variant="secondary" onClick={() => setConfirmCopy(true)} isPending={copyPreset.isPending} icon={<Copy size={15} />} pendingLabel="Copying…">
            Copy
          </ActionButton>
        )}
        {!isNew && (
          <ActionButton variant="secondary" onClick={() => setConfirmDelete(true)} isPending={deletePreset.isPending} icon={<Trash2 size={15} />} className="border-red-200 text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10">
            Delete
          </ActionButton>
        )}
        <ActionButton
          onClick={() => save.mutate()}
          isPending={save.isPending}
          isSuccess={save.isSuccess}
          disabled={!name}
          icon={<Save size={15} />}
          pendingLabel="Saving…"
        >
          Save
        </ActionButton>
      </div>


      <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
        <div className="min-w-0 flex-1 space-y-5">
          <Section title="General">
            <Field label="Name *">
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={platform === "leap" ? "Course look" : "My upload preset"}
                className={FILTER_CONTROL}
              />
            </Field>

            <Field label="Description">
              <input
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Optional"
                className={FILTER_CONTROL}
              />
            </Field>

            <Field label="Platform">
              <div className="flex flex-wrap gap-2">
                {platformChoices.map((o) => {
                  const selected = platform === o.value;
                  return (
                    <button
                      key={o.value}
                      type="button"
                      onClick={() => changePlatform(o.value)}
                      disabled={!isNew}
                      className={cn(
                        "min-w-[5.5rem] flex-1 rounded-xl border px-2 py-2 text-sm transition-colors sm:flex-none sm:min-w-[7rem]",
                        selected
                          ? "border-primary bg-primary font-medium text-white"
                          : o.featured
                            ? "border-primary/45 bg-primary/5 font-semibold tracking-wide text-primary hover:bg-primary/10"
                            : "border-border bg-card font-medium text-secondary-foreground hover:bg-muted",
                        !isNew && "disabled:opacity-40",
                      )}
                    >
                      {o.label}
                    </button>
                  );
                })}
              </div>
            </Field>

            {platform !== "leap" && (
              <Field label="Credential">
                {creds.length === 0 ? (
                  <CreatePlaceholder href="/credentials" label="Add credentials" />
                ) : (
                  <NativeSelect
                    value={credId}
                    onChange={(e) => setCredId(Number(e.target.value) || "")}
                  >
                    <option value="">— Select credential —</option>
                    {creds.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.account_name ?? `Credential #${c.id}`}
                      </option>
                    ))}
                  </NativeSelect>
                )}
              </Field>
            )}
          </Section>

          <Section title="Platform settings">
          {platform === "youtube" && (
            <YouTubeFields
              value={meta as YouTubeFieldsValue}
              onChange={patchMeta}
              showThumbnail
              showMadeForKids
              showExtended
              showDisplayConfig
            />
          )}

          {platform === "vk" && (
            <VkFields
              value={meta as VkFieldsValue}
              onChange={patchMeta}
              showThumbnail
              showPrivacyComment
              showWallpost
              showExtended
              showDisplayConfig
            />
          )}

          {platform === "leap" && (
            <LeapLookFields
              value={meta as LeapFieldsValue}
              onChange={patchMeta}
              showPublish
            />
          )}

          {platform === "yandex_disk" && (
            <YandexDiskFields
              value={meta as YandexDiskFieldsValue}
              onChange={patchMeta}
              showExtended
              credentialId={credId}
            />
          )}

          <div className="space-y-2 border-t border-border pt-4">
            <ActionButton
              variant="secondary"
              onClick={handleRenderPreview}
              isPending={renderPreviewLoading}
              icon={<Eye size={15} />}
              pendingLabel="Rendering…"
            >
              Preview render
            </ActionButton>
            {renderPreview ? <MetadataPreviewResultBox preview={renderPreview} /> : null}
          </div>
          </Section>
        </div>

        <div className="w-full space-y-4 lg:w-72 lg:shrink-0">
          <div className="rounded-2xl border border-border bg-card p-4 shadow-sm">
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Status</h2>
            <div className="mb-4 flex items-center gap-2">
              <span className={cn("inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium", statusColor)}>
                {statusLabel}
              </span>
            </div>
            <div className="space-y-1">
              <div className="my-3 border-t border-border" role="separator" />
              <Toggle
                label="Active"
                hint="Skipped when off."
                checked={isActive}
                onChange={setIsActive}
                className="rounded-xl px-2 py-2 transition-colors hover:bg-muted"
              />
            </div>
          </div>

          {!isNew && existing && (
            <div className="rounded-2xl border border-border bg-card p-4 shadow-sm">
              <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Info</h2>
              <div className="space-y-2 text-sm">
                <InfoRow
                  label="Created"
                  value={new Date(existing.created_at).toLocaleDateString("en-GB", {
                    day: "numeric",
                    month: "short",
                    year: "numeric",
                  })}
                />
                <InfoRow
                  label="Updated"
                  value={new Date(existing.updated_at).toLocaleDateString("en-GB", {
                    day: "numeric",
                    month: "short",
                    year: "numeric",
                  })}
                />
              </div>
            </div>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={confirmCopy}
        title="Copy preset?"
        description="A new copy will be created with the same settings."
        confirmLabel="Create copy"
        onConfirm={() => { setConfirmCopy(false); copyPreset.mutate(); }}
        onCancel={() => setConfirmCopy(false)}
      />

      <ConfirmDialog
        open={confirmDelete}
        title="Delete preset?"
        description="This preset will be permanently deleted and automatically removed from all templates that reference it."
        confirmLabel="Delete"
        danger
        onConfirm={() => { setConfirmDelete(false); deletePreset.mutate(); }}
        onCancel={() => setConfirmDelete(false)}
      />

      <ConfirmDialog
        open={confirmLeave}
        title="Leave without saving?"
        description="You have unsaved changes. They will be lost if you leave."
        confirmLabel="Leave"
        cancelLabel="Stay"
        danger
        onConfirm={() => { setConfirmLeave(false); router.push(pendingHref); }}
        onCancel={() => setConfirmLeave(false)}
      />

      {toast && <Toast key={toast.serial} type={toast.type} message={toast.msg} exiting={toast.exiting} onDismiss={dismissToast} />}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-4 rounded-2xl border border-border bg-card p-5 shadow-sm">
      <h2 className="text-sm font-semibold text-secondary-foreground">{title}</h2>
      {children}
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium text-foreground">{value}</span>
    </div>
  );
}
