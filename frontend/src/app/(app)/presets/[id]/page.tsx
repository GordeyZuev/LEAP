"use client";

import { use, useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Save } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/api/client";
import { TagInput } from "@/components/ui/tag-input";

type Platform = "youtube" | "vk" | "yandex_disk";

interface CredentialItem {
  id: number;
  platform: string;
  account_name: string | null;
}

// Platform-specific metadata interfaces
interface YouTubeMeta {
  title_template: string;
  description_template: string;
  privacy: "public" | "private" | "unlisted";
  category_id: string;
  playlist_id: string;
  tags: string[];
  made_for_kids: boolean;
}

interface VKMeta {
  title_template: string;
  description_template: string;
  privacy_view: number;
  group_id: string;
  album_id: string;
}

interface YandexDiskMeta {
  folder_path_template: string;
  filename_template: string;
  overwrite: boolean;
  publish: boolean;
}

type PresetMeta = YouTubeMeta | VKMeta | YandexDiskMeta;

interface PresetForm {
  name: string;
  description: string;
  platform: Platform;
  credential_id: number | "";
  preset_metadata: PresetMeta;
}

const DEFAULT_YT_META: YouTubeMeta = {
  title_template: "",
  description_template: "",
  privacy: "unlisted",
  category_id: "27",
  playlist_id: "",
  tags: [],
  made_for_kids: false,
};

const DEFAULT_VK_META: VKMeta = {
  title_template: "",
  description_template: "",
  privacy_view: 0,
  group_id: "",
  album_id: "",
};

const DEFAULT_YD_META: YandexDiskMeta = {
  folder_path_template: "/Video/{{ display_name }}",
  filename_template: "",
  overwrite: false,
  publish: false,
};

function getDefaultMeta(platform: Platform): PresetMeta {
  if (platform === "youtube") return { ...DEFAULT_YT_META };
  if (platform === "vk") return { ...DEFAULT_VK_META };
  return { ...DEFAULT_YD_META };
}

/** API may return null for optional strings or tags; React inputs need defined strings / arrays. */
function coercePresetMeta(platform: Platform, raw: unknown): PresetMeta {
  const base = getDefaultMeta(platform);
  if (!raw || typeof raw !== "object") return base;
  const o = raw as Record<string, unknown>;
  if (platform === "youtube") {
    const priv = o.privacy;
    const privacy =
      priv === "public" || priv === "private" || priv === "unlisted" ? priv : (base as YouTubeMeta).privacy;
    const tagList = o.tags;
    return {
      title_template: o.title_template != null ? String(o.title_template) : "",
      description_template: o.description_template != null ? String(o.description_template) : "",
      privacy,
      category_id: o.category_id != null ? String(o.category_id) : (base as YouTubeMeta).category_id,
      playlist_id: o.playlist_id != null ? String(o.playlist_id) : "",
      tags: Array.isArray(tagList) ? tagList.filter((t): t is string => typeof t === "string") : [],
      made_for_kids: Boolean(o.made_for_kids),
    };
  }
  if (platform === "vk") {
    const pv = o.privacy_view;
    return {
      title_template: o.title_template != null ? String(o.title_template) : "",
      description_template: o.description_template != null ? String(o.description_template) : "",
      privacy_view: typeof pv === "number" && !Number.isNaN(pv) ? pv : Number(pv) || 0,
      group_id: o.group_id != null ? String(o.group_id) : "",
      album_id: o.album_id != null ? String(o.album_id) : "",
    };
  }
  return {
    folder_path_template:
      o.folder_path_template != null ? String(o.folder_path_template) : (base as YandexDiskMeta).folder_path_template,
    filename_template: o.filename_template != null ? String(o.filename_template) : "",
    overwrite: Boolean(o.overwrite),
    publish: Boolean(o.publish),
  };
}

const PLATFORM_OPTIONS: { value: Platform; label: string }[] = [
  { value: "youtube",     label: "YouTube" },
  { value: "vk",         label: "VK Video" },
  { value: "yandex_disk",label: "Yandex Disk" },
];

const YT_PRIVACY_OPTIONS = [
  { value: "public", label: "Public" },
  { value: "unlisted", label: "Unlisted" },
  { value: "private", label: "Private" },
];

const VK_PRIVACY_OPTIONS = [
  { value: 0, label: "Everyone" },
  { value: 1, label: "Friends" },
  { value: 2, label: "Friends of friends" },
  { value: 3, label: "Only me" },
];

export default function PresetEditorPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const isNew = id === "new";
  const router = useRouter();
  const qc = useQueryClient();

  const [form, setForm] = useState<PresetForm>({
    name: "",
    description: "",
    platform: "youtube",
    credential_id: "",
    preset_metadata: { ...DEFAULT_YT_META },
  });
  const [saveError, setSaveError] = useState("");

  const { data: existing } = useQuery({
    queryKey: ["preset", id],
    queryFn: async () => {
      const res = await apiClient.get(`/presets/${id}`);
      return res.data;
    },
    enabled: !isNew,
  });

  const { data: credsData } = useQuery<{ items: CredentialItem[] }>({
    queryKey: ["credentials-list"],
    queryFn: async () => {
      const res = await apiClient.get("/credentials?per_page=50");
      return res.data;
    },
  });

  useEffect(() => {
    if (!existing) return;
    const platform = (existing.platform ?? "youtube") as Platform;
    setForm({
      name: existing.name ?? "",
      description: existing.description ?? "",
      platform,
      credential_id: existing.credential_id ?? "",
      preset_metadata: coercePresetMeta(platform, existing.preset_metadata),
    });
  }, [existing]);

  const save = useMutation({
    mutationFn: async (data: PresetForm) => {
      const body = {
        name: data.name,
        description: data.description || undefined,
        platform: data.platform,
        credential_id: data.credential_id || undefined,
        preset_metadata: data.preset_metadata,
      };
      if (isNew) {
        const res = await apiClient.post("/presets", body);
        return res.data;
      } else {
        const res = await apiClient.patch(`/presets/${id}`, body);
        return res.data;
      }
    },
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: ["presets"] });
      setSaveError("");
      if (isNew) router.push(`/presets/${result.id}`);
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setSaveError(typeof detail === "string" ? detail : "Failed to save preset");
    },
  });

  function changePlatform(p: Platform) {
    setForm((f) => ({ ...f, platform: p, preset_metadata: getDefaultMeta(p), credential_id: "" }));
  }

  const creds = (credsData?.items ?? []).filter((c) => {
    if (form.platform === "youtube") return c.platform === "youtube";
    if (form.platform === "vk") return c.platform === "vk_video";
    if (form.platform === "yandex_disk") return c.platform === "yandex_disk";
    return false;
  });

  const meta = form.preset_metadata;

  function setMeta<K extends string>(key: K, value: unknown) {
    setForm((f) => ({ ...f, preset_metadata: { ...f.preset_metadata, [key]: value } as PresetMeta }));
  }

  return (
    <div className="w-full min-w-0 p-6 sm:p-8">
      {/* Header */}
      <div className="flex items-center gap-4 mb-6 flex-wrap">
        <Link href="/presets" className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700 transition-colors">
          <ArrowLeft size={16} /> Presets
        </Link>
        <span className="text-gray-300">/</span>
        <h1 className="text-lg font-semibold text-gray-900 flex-1">
          {isNew ? "New preset" : (existing?.name ?? "…")}
        </h1>
        <button
          onClick={() => save.mutate(form)}
          disabled={save.isPending || !form.name}
          className="flex items-center gap-2 bg-[#224C87] text-white px-4 py-2 rounded-xl text-sm font-medium hover:bg-[#1a3d6e] disabled:opacity-50 transition-colors"
        >
          <Save size={15} />
          {save.isPending ? "Saving…" : "Save"}
        </button>
      </div>

      {saveError && (
        <div className="mb-4 px-4 py-3 bg-red-50 border border-red-200 rounded-xl text-sm text-red-600">{saveError}</div>
      )}

      <div className="space-y-5">
        {/* General */}
        <div className="bg-white rounded-2xl border border-[#D9D9D9] shadow-sm p-5 space-y-4">
          <h2 className="text-sm font-semibold text-gray-700">General</h2>
          <FormField label="Name *">
            <input
              type="text"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="My YouTube preset"
              className={inputCls}
            />
          </FormField>
          <FormField label="Description">
            <input
              type="text"
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              placeholder="Optional"
              className={inputCls}
            />
          </FormField>
          <FormField label="Platform">
            <div className="flex gap-2">
              {PLATFORM_OPTIONS.map((o) => (
                <button
                  key={o.value}
                  type="button"
                  onClick={() => changePlatform(o.value)}
                  disabled={!isNew}
                  className={cn(
                    "flex-1 py-2 rounded-xl text-sm font-medium border transition-colors",
                    form.platform === o.value
                      ? "bg-[#224C87] text-white border-[#224C87]"
                      : "bg-white text-gray-600 border-[#D9D9D9] hover:bg-gray-50 disabled:opacity-40"
                  )}
                >
                  {o.label}
                </button>
              ))}
            </div>
          </FormField>
          <FormField label="Credential">
            {creds.length === 0 ? (
              <p className="text-sm text-gray-400">
                No {PLATFORM_OPTIONS.find((o) => o.value === form.platform)?.label} credentials.{" "}
                <Link href="/credentials" className="text-[#224C87] hover:underline">Add credentials →</Link>
              </p>
            ) : (
              <select
                value={form.credential_id}
                onChange={(e) => setForm((f) => ({ ...f, credential_id: Number(e.target.value) || "" }))}
                className={cn(inputCls, "bg-white")}
              >
                <option value="">— Select credential —</option>
                {creds.map((c) => (
                  <option key={c.id} value={c.id}>{c.account_name ?? `Credential #${c.id}`}</option>
                ))}
              </select>
            )}
          </FormField>
        </div>

        {/* Platform-specific settings */}
        <div className="bg-white rounded-2xl border border-[#D9D9D9] shadow-sm p-5 space-y-4">
          <h2 className="text-sm font-semibold text-gray-700">Platform settings</h2>

          {/* Title + description (all platforms) */}
          <FormField label="Title template" hint="Jinja2: {{ display_name }}, {{ date }}, {{ topic }}">
            <input
              type="text"
              value={"title_template" in meta ? (meta as { title_template: string }).title_template : ""}
              onChange={(e) => setMeta("title_template", e.target.value)}
              placeholder="{{ display_name }} | {{ topic }}"
              className={inputCls}
            />
          </FormField>
          {"description_template" in meta && (
            <FormField label="Description template">
              <textarea
                value={(meta as { description_template: string }).description_template}
                onChange={(e) => setMeta("description_template", e.target.value)}
                rows={4}
                placeholder="Recording from {{ date }}\n\n{{ topics }}"
                className={cn(inputCls, "resize-none font-mono text-xs")}
              />
            </FormField>
          )}

          {/* YouTube-specific */}
          {form.platform === "youtube" && (
            <>
              <FormField label="Privacy">
                <select value={(meta as YouTubeMeta).privacy} onChange={(e) => setMeta("privacy", e.target.value)} className={cn(inputCls, "bg-white")}>
                  {YT_PRIVACY_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </FormField>
              <FormField label="Playlist ID">
                <input type="text" value={(meta as YouTubeMeta).playlist_id} onChange={(e) => setMeta("playlist_id", e.target.value)} placeholder="PLxxxxxxxx" className={inputCls} />
              </FormField>
              <FormField label="Tags">
                <TagInput tags={(meta as YouTubeMeta).tags} onChange={(v) => setMeta("tags", v)} placeholder="Add tag…" />
              </FormField>
              <Toggle label="Made for kids" checked={(meta as YouTubeMeta).made_for_kids} onChange={(v) => setMeta("made_for_kids", v)} />
            </>
          )}

          {/* VK-specific */}
          {form.platform === "vk" && (
            <>
              <FormField label="Privacy view">
                <select value={(meta as VKMeta).privacy_view} onChange={(e) => setMeta("privacy_view", Number(e.target.value))} className={cn(inputCls, "bg-white")}>
                  {VK_PRIVACY_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </FormField>
              <FormField label="Group ID">
                <input type="text" value={(meta as VKMeta).group_id} onChange={(e) => setMeta("group_id", e.target.value)} placeholder="123456789" className={inputCls} />
              </FormField>
              <FormField label="Album ID">
                <input type="text" value={(meta as VKMeta).album_id} onChange={(e) => setMeta("album_id", e.target.value)} placeholder="Album ID" className={inputCls} />
              </FormField>
            </>
          )}

          {/* Yandex Disk-specific */}
          {form.platform === "yandex_disk" && (
            <>
              <FormField label="Folder path *" hint="Jinja2: {{ display_name }}, {{ date }}">
                <input type="text" value={(meta as YandexDiskMeta).folder_path_template} onChange={(e) => setMeta("folder_path_template", e.target.value)} placeholder="/Video/{{ display_name }}" className={inputCls} />
              </FormField>
              <FormField label="Filename template">
                <input type="text" value={(meta as YandexDiskMeta).filename_template} onChange={(e) => setMeta("filename_template", e.target.value)} placeholder="{{ display_name }}.mp4" className={inputCls} />
              </FormField>
              <Toggle label="Overwrite existing" checked={(meta as YandexDiskMeta).overwrite} onChange={(v) => setMeta("overwrite", v)} />
              <Toggle label="Publish publicly" checked={(meta as YandexDiskMeta).publish} onChange={(v) => setMeta("publish", v)} />
            </>
          )}
        </div>
      </div>
    </div>
  );
}

const inputCls = "w-full px-4 py-2.5 rounded-xl border border-[#D9D9D9] text-sm outline-none focus:border-[#224C87] focus:ring-2 focus:ring-[#224C87]/10 transition-colors";

function FormField({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1.5">{label}</label>
      {hint && <p className="text-xs text-gray-400 mb-1.5">{hint}</p>}
      {children}
    </div>
  );
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center justify-between py-2 cursor-pointer">
      <span className="text-sm font-medium text-gray-700">{label}</span>
      <button
        type="button"
        onClick={() => onChange(!checked)}
        className={cn("relative inline-flex h-6 w-11 items-center rounded-full transition-colors", checked ? "bg-[#224C87]" : "bg-gray-200")}
      >
        <span className={cn("inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform", checked ? "translate-x-6" : "translate-x-1")} />
      </button>
    </label>
  );
}
