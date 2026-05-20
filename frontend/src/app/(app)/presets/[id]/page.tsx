"use client";

import { use, useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Save, Copy, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/api/client";
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
} from "@/components/platforms/platform-fields";
import { FILTER_CONTROL, FILTER_LABEL } from "@/lib/filter-field-classes";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { usePlatforms } from "@/hooks/use-references";

type Platform = "youtube" | "vk" | "yandex_disk";

interface CredentialItem {
  id: number;
  platform: string;
  account_name: string | null;
}

// ---------------------------------------------------------------------------
// Per-platform meta helpers
// ---------------------------------------------------------------------------

type PlatformMeta = YouTubeFieldsValue | VkFieldsValue | YandexDiskFieldsValue;

function getDefaultMeta(platform: Platform): PlatformMeta {
  if (platform === "youtube")     return { ...DEFAULT_YOUTUBE_FIELDS };
  if (platform === "vk")          return { ...DEFAULT_VK_FIELDS };
  return { ...DEFAULT_YANDEX_DISK_FIELDS };
}

function coerceMeta(platform: Platform, raw: unknown): PlatformMeta {
  const base = getDefaultMeta(platform);
  if (!raw || typeof raw !== "object") return base;
  const o = raw as Record<string, unknown>;

  if (platform === "youtube") {
    const priv = o.privacy;
    const privacy =
      priv === "public" || priv === "private" || priv === "unlisted"
        ? priv
        : (base as YouTubeFieldsValue).privacy;
    const tagList = o.tags;
    return {
      title_template:       o.title_template       != null ? String(o.title_template)       : "",
      description_template: o.description_template != null ? String(o.description_template) : "",
      privacy,
      category_id:    o.category_id    != null ? String(o.category_id)    : "",
      playlist_id:    o.playlist_id    != null ? String(o.playlist_id)    : "",
      thumbnail_name: o.thumbnail_name != null ? String(o.thumbnail_name) : "",
      tags:           Array.isArray(tagList) ? tagList.filter((t): t is string => typeof t === "string") : [],
      made_for_kids:  Boolean(o.made_for_kids),
    } satisfies YouTubeFieldsValue;
  }

  if (platform === "vk") {
    const pv = o.privacy_view;
    const pc = o.privacy_comment;
    return {
      title_template:       o.title_template       != null ? String(o.title_template)       : "",
      description_template: o.description_template != null ? String(o.description_template) : "",
      privacy_view:    pv != null ? String(pv)    : "",
      privacy_comment: pc != null ? String(pc)    : "",
      group_id:        o.group_id    != null ? String(o.group_id)    : "",
      album_id:        o.album_id    != null ? String(o.album_id)    : "",
      thumbnail_name:  o.thumbnail_name != null ? String(o.thumbnail_name) : "",
      wallpost:        Boolean(o.wallpost),
    } satisfies VkFieldsValue;
  }

  return {
    folder_path_template: o.folder_path_template != null ? String(o.folder_path_template) : (base as YandexDiskFieldsValue).folder_path_template,
    filename_template:    o.filename_template    != null ? String(o.filename_template)    : "",
    overwrite: Boolean(o.overwrite),
    publish:   Boolean(o.publish),
  } satisfies YandexDiskFieldsValue;
}

// ---------------------------------------------------------------------------
// Serialise meta back to API format
// ---------------------------------------------------------------------------

function serialiseMeta(platform: Platform, meta: PlatformMeta): Record<string, unknown> {
  if (platform === "vk") {
    const vk = meta as VkFieldsValue;
    return {
      ...vk,
      privacy_view:    vk.privacy_view    !== "" ? Number(vk.privacy_view)    : undefined,
      privacy_comment: vk.privacy_comment !== "" ? Number(vk.privacy_comment) : undefined,
    };
  }
  return meta as unknown as Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

export default function PresetEditorPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const isNew = id === "new";
  const router = useRouter();
  const qc = useQueryClient();

  const { data: platformOptions = [] } = usePlatforms();

  const [name,        setName]        = useState("");
  const [description, setDescription] = useState("");
  const [platform,    setPlatform]    = useState<Platform>("youtube");
  const [credId,      setCredId]      = useState<number | "">("");
  const [meta,        setMeta]        = useState<PlatformMeta>({ ...DEFAULT_YOUTUBE_FIELDS });
  const [saveError,   setSaveError]   = useState("");

  const savedSnapshot = useRef<string>(
    JSON.stringify({ name: "", description: "", credId: "", meta: { ...DEFAULT_YOUTUBE_FIELDS } })
  );
  const [confirmCopy, setConfirmCopy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmLeave, setConfirmLeave] = useState(false);
  const [pendingHref, setPendingHref] = useState("");

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
    const p = (existing.platform ?? "youtube") as Platform;
    const newName = existing.name ?? "";
    const newDesc = existing.description ?? "";
    const newCredId = existing.credential_id ?? "";
    const newMeta = coerceMeta(p, existing.preset_metadata);
    setPlatform(p);
    setName(newName);
    setDescription(newDesc);
    setCredId(newCredId);
    setMeta(newMeta);
    savedSnapshot.current = JSON.stringify({ name: newName, description: newDesc, credId: newCredId, meta: newMeta });
  }, [existing]);
  /* eslint-enable react-hooks/set-state-in-effect */

  const save = useMutation({
    mutationFn: async () => {
      const body = {
        name,
        description: description || undefined,
        platform,
        credential_id: credId || undefined,
        preset_metadata: serialiseMeta(platform, meta),
      };
      if (isNew) {
        return (await apiClient.post("/presets", body)).data;
      } else {
        return (await apiClient.patch(`/presets/${id}`, body)).data;
      }
    },
    onSuccess: (result) => {
      savedSnapshot.current = JSON.stringify({ name, description, credId, meta });
      qc.invalidateQueries({ queryKey: ["presets"] });
      setSaveError("");
      if (isNew) router.push(`/presets/${result.id}`);
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setSaveError(typeof detail === "string" ? detail : "Failed to save preset");
    },
  });

  const copyPreset = useMutation({
    mutationFn: () =>
      apiClient.post<{ id: number }>(`/presets/${id}/copy`).then((r) => r.data),
    onSuccess: (result) => router.push(`/presets/${result.id}`),
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setSaveError(typeof detail === "string" ? detail : "Failed to copy preset");
    },
  });

  const deletePreset = useMutation({
    mutationFn: () => apiClient.delete(`/presets/${id}`),
    onSuccess: () => router.push("/presets"),
    onError: () => setSaveError("Failed to delete preset"),
  });

  function changePlatform(p: Platform) {
    setPlatform(p);
    setMeta(getDefaultMeta(p));
    setCredId("");
  }

  function patchMeta(patch: Partial<PlatformMeta>) {
    setMeta((prev) => ({ ...prev, ...patch } as PlatformMeta));
  }

  const creds = (credsData?.items ?? []).filter((c) => {
    if (platform === "youtube")     return c.platform === "youtube";
    if (platform === "vk")          return c.platform === "vk_video";
    if (platform === "yandex_disk") return c.platform === "yandex_disk";
    return false;
  });

  const isDirty =
    JSON.stringify({ name, description, credId, meta }) !== savedSnapshot.current;

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
          className="flex items-center gap-1.5 text-sm text-gray-500 transition-colors hover:text-gray-700"
        >
          <ArrowLeft size={16} /> Presets
        </button>
        <span className="text-gray-300">/</span>
        <h1 className="flex-1 text-lg font-semibold text-gray-900">
          {isNew ? "New preset" : (existing?.name ?? "…")}
        </h1>
        {!isNew && (
          <button
            onClick={() => setConfirmCopy(true)}
            disabled={copyPreset.isPending}
            className="flex items-center gap-2 rounded-xl border border-[#D9D9D9] bg-white px-4 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50 disabled:opacity-50"
          >
            <Copy size={15} />
            {copyPreset.isPending ? "Copying…" : "Copy"}
          </button>
        )}
        {!isNew && (
          <button
            onClick={() => setConfirmDelete(true)}
            disabled={deletePreset.isPending}
            className="flex items-center gap-2 rounded-xl border border-red-200 bg-white px-4 py-2 text-sm font-medium text-red-500 transition-colors hover:bg-red-50 disabled:opacity-50"
          >
            <Trash2 size={15} />
            Delete
          </button>
        )}
        <button
          onClick={() => save.mutate()}
          disabled={save.isPending || !name}
          className="flex items-center gap-2 rounded-xl bg-[#224C87] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[#1a3d6e] disabled:opacity-50"
        >
          <Save size={15} />
          {save.isPending ? "Saving…" : "Save"}
        </button>
      </div>

      {saveError && (
        <div className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
          {saveError}
        </div>
      )}

      <div className="space-y-5">
        {/* General */}
        <div className="space-y-4 rounded-2xl border border-[#D9D9D9] bg-white p-5 shadow-sm">
          <h2 className="text-sm font-semibold text-gray-700">General</h2>

          <div>
            <label className={FILTER_LABEL}>Name *</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="My YouTube preset"
              className={FILTER_CONTROL}
            />
          </div>

          <div>
            <label className={FILTER_LABEL}>Description</label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional"
              className={FILTER_CONTROL}
            />
          </div>

          <div>
            <label className={FILTER_LABEL}>Platform</label>
            <div className="mt-1 flex gap-2">
              {platformOptions.map((o) => (
                <button
                  key={o.value}
                  type="button"
                  onClick={() => changePlatform(o.value as Platform)}
                  disabled={!isNew}
                  className={cn(
                    "flex-1 rounded-xl border py-2 text-sm font-medium transition-colors",
                    platform === o.value
                      ? "border-[#224C87] bg-[#224C87] text-white"
                      : "border-[#D9D9D9] bg-white text-gray-600 hover:bg-gray-50 disabled:opacity-40"
                  )}
                >
                  {o.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className={FILTER_LABEL}>Credential</label>
            {creds.length === 0 ? (
              <p className="mt-1 text-sm text-gray-400">
                No {platformOptions.find((o) => o.value === platform)?.label} credentials.{" "}
                <Link href="/credentials" className="text-[#224C87] hover:underline">
                  Add credentials →
                </Link>
              </p>
            ) : (
              <select
                value={credId}
                onChange={(e) => setCredId(Number(e.target.value) || "")}
                className={cn(FILTER_CONTROL, "bg-white")}
              >
                <option value="">— Select credential —</option>
                {creds.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.account_name ?? `Credential #${c.id}`}
                  </option>
                ))}
              </select>
            )}
          </div>
        </div>

        {/* Platform-specific settings */}
        <div className="space-y-4 rounded-2xl border border-[#D9D9D9] bg-white p-5 shadow-sm">
          <h2 className="text-sm font-semibold text-gray-700">Platform settings</h2>

          {platform === "youtube" && (
            <YouTubeFields
              value={meta as YouTubeFieldsValue}
              onChange={patchMeta}
              showThumbnail
              showMadeForKids
            />
          )}

          {platform === "vk" && (
            <VkFields
              value={meta as VkFieldsValue}
              onChange={patchMeta}
              showThumbnail
              showPrivacyComment
              showWallpost
            />
          )}

          {platform === "yandex_disk" && (
            <YandexDiskFields
              value={meta as YandexDiskFieldsValue}
              onChange={patchMeta}
            />
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
        description="This preset will be permanently deleted. Templates referencing it will lose this preset assignment."
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
    </div>
  );
}
