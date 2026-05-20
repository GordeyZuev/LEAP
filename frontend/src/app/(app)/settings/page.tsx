"use client";

import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Save, RefreshCw, ChevronDown, LogOut, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import { apiClient } from "@/api/client";
import {
  FILTER_CONTROL,
  FILTER_LABEL,
  FILTER_SEGMENT_ACTIVE,
  FILTER_SEGMENT_BTN,
  FILTER_SEGMENT_IDLE,
  FILTER_SEGMENT_WRAP,
} from "@/lib/filter-field-classes";
import { TagInput } from "@/components/ui/tag-input";
import { TemplateField } from "@/components/platforms/platform-fields";
import { useGranularities, useLanguages, useQualities, useTimezones } from "@/hooks/use-references";
import { TOAST_LONG, TOAST_SHORT } from "@/lib/constants";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface UserMe {
  id: string;
  email: string;
  full_name: string | null;
  timezone: string;
  role: string;
  created_at: string;
}

interface TrimmingConfig {
  enable_trimming: boolean;
  audio_detection: boolean;
  silence_threshold: number;
  min_silence_duration: number;
  padding_before: number;
  padding_after: number;
}

interface TranscriptionConfig {
  enable_transcription: boolean;
  language: string;
  prompt: string;
  vocabulary: string[];
  allow_errors: boolean;
  enable_topics: boolean;
  granularity: string;
  questions_count: number;
  enable_subtitles: boolean;
  enable_translation: boolean;
  translation_language: string;
}

interface DownloadConfig {
  auto_download: boolean;
  max_file_size_mb: number;
  quality: string;
  retry_attempts: number;
  retry_delay: number;
}

interface UploadConfig {
  auto_upload: boolean;
  upload_captions: boolean;
}

interface MetadataConfig {
  title_template: string;
  description_template: string;
  date_format: string;
  tags: string[];
}

interface RetentionConfig {
  soft_delete_days: number;
  hard_delete_days: number;
  auto_expire_days: number;
}

interface UserConfig {
  config_data: {
    trimming: TrimmingConfig;
    transcription: TranscriptionConfig;
    download: DownloadConfig;
    upload: UploadConfig;
    metadata: MetadataConfig;
    retention: RetentionConfig;
  };
}

interface QuotaStatus {
  subscription?: {
    plan: { display_name: string };
    expires_at?: string | null;
  } | null;
  current_usage?: {
    recordings_count: number;
    storage_bytes: number;
    concurrent_tasks_count: number;
  } | null;
  recordings: { used?: number | null; limit?: number | null; available?: number | null };
  storage: { used_gb?: number | null; limit_gb?: number | null; available_gb?: number | null };
  concurrent_tasks: { used?: number | null; limit?: number | null };
  automation_jobs: { used?: number | null; limit?: number | null };
  is_overage_enabled: boolean;
}

interface UserStats {
  recordings_total: number;
  recordings_by_status: Record<string, number>;
  transcription_total_seconds: number;
  storage_gb: number;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DEFAULT_TRIMMING: TrimmingConfig = {
  enable_trimming: true,
  audio_detection: true,
  silence_threshold: -40.0,
  min_silence_duration: 2.0,
  padding_before: 5.0,
  padding_after: 5.0,
};

const DEFAULT_TRANSCRIPTION: TranscriptionConfig = {
  enable_transcription: true,
  language: "ru",
  prompt: "",
  vocabulary: [],
  allow_errors: false,
  enable_topics: true,
  granularity: "long",
  questions_count: 3,
  enable_subtitles: true,
  enable_translation: false,
  translation_language: "en",
};

const DEFAULT_DOWNLOAD: DownloadConfig = {
  auto_download: false,
  max_file_size_mb: 5000,
  quality: "high",
  retry_attempts: 3,
  retry_delay: 5,
};

const DEFAULT_UPLOAD: UploadConfig = {
  auto_upload: false,
  upload_captions: true,
};

const DEFAULT_METADATA: MetadataConfig = {
  title_template: "{{ display_name }} | {{ topic }} ({{ date }})",
  description_template: "Recording from {{ date }}",
  date_format: "DD.MM.YYYY",
  tags: [],
};

const DEFAULT_RETENTION: RetentionConfig = {
  soft_delete_days: 3,
  hard_delete_days: 30,
  auto_expire_days: 90,
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function extractError(err: unknown): string {
  type ApiErr = { response?: { data?: { detail?: string | { msg: string }[] } } };
  const e = err as ApiErr | null;
  const detail = e?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail[0]?.msg ?? "Unknown error";
  return "Request failed";
}

function fmtNum(n: number | null | undefined, decimals = 0): string {
  if (n == null) return "∞";
  return decimals > 0 ? n.toFixed(decimals) : String(n);
}

// ---------------------------------------------------------------------------
// UI atoms
// ---------------------------------------------------------------------------

function SectionCard({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-2xl border border-[#D9D9D9] shadow-sm">
      <div className="flex items-center justify-between px-6 py-4 border-b border-[#D9D9D9]">
        <h2 className="text-sm font-semibold text-gray-900">{title}</h2>
        {action}
      </div>
      <div className="p-6 space-y-5">{children}</div>
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <label className={cn(FILTER_LABEL, "mb-1.5")}>{label}</label>
      {hint && <p className="text-xs text-gray-400 mb-1.5">{hint}</p>}
      {children}
    </div>
  );
}

function Toggle({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between py-1 gap-4">
      <div className="min-w-0">
        <p className="text-sm font-medium text-gray-700 leading-snug">{label}</p>
        {hint && <p className="text-xs text-gray-400 leading-snug">{hint}</p>}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={cn(
          "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors",
          checked ? "bg-[#224C87]" : "bg-gray-200"
        )}
      >
        <span
          className={cn(
            "inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform",
            checked ? "translate-x-6" : "translate-x-1"
          )}
        />
      </button>
    </div>
  );
}

function Collapsible({
  label,
  open,
  onToggle,
  children,
}: {
  label: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-[#EAEAEA] bg-[#FAFAFA]">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors"
      >
        {label}
        <ChevronDown
          size={14}
          className={cn("shrink-0 text-gray-400 transition-transform", open && "rotate-180")}
        />
      </button>
      {open && (
        <div className="space-y-4 border-t border-[#EAEAEA] px-4 pb-4 pt-4">{children}</div>
      )}
    </div>
  );
}

function QuotaBar({
  label,
  used,
  limit,
  suffix = "",
}: {
  label: string;
  used: number;
  limit: number | null;
  suffix?: string;
}) {
  const pct = limit ? Math.min((used / limit) * 100, 100) : 0;
  const warn = pct >= 80;
  const crit = pct >= 95;
  const usedStr = suffix ? used.toFixed(2) : String(used);
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs font-medium text-gray-600">{label}</span>
        <span
          className={cn(
            "text-xs tabular-nums",
            crit ? "text-red-500" : warn ? "text-amber-500" : "text-gray-500"
          )}
        >
          {usedStr}{suffix} / {fmtNum(limit)}{limit !== null ? suffix : ""}
        </span>
      </div>
      {limit !== null ? (
        <div className="h-1.5 w-full rounded-full bg-gray-100 overflow-hidden">
          <div
            className={cn(
              "h-full rounded-full transition-all duration-500",
              crit ? "bg-red-400" : warn ? "bg-amber-400" : "bg-[#224C87]"
            )}
            style={{ width: `${pct}%` }}
          />
        </div>
      ) : (
        <div className="h-1.5 w-full rounded-full bg-gray-100 overflow-hidden">
          <div className="h-full w-0 rounded-full bg-[#224C87]" />
        </div>
      )}
    </div>
  );
}

function StatChip({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <p className="text-xs text-gray-400 mb-0.5">{label}</p>
      <p className="text-base font-semibold text-gray-900 tabular-nums">{value}</p>
    </div>
  );
}

const BTN_PRIMARY =
  "flex items-center gap-2 bg-[#224C87] text-white px-4 py-2 rounded-xl text-sm font-medium hover:bg-[#1a3d6e] disabled:opacity-50 transition-colors";
const BTN_SECONDARY =
  "flex items-center gap-2 px-4 py-2 rounded-xl border border-[#D9D9D9] text-sm font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50 transition-colors";

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function SettingsPage() {
  const qc = useQueryClient();
  const router = useRouter();

  // ── Profile ───────────────────────────────────────────────────────────────
  const [profile, setProfile] = useState({ full_name: "", email: "", timezone: "" });
  const [profileSuccess, setProfileSuccess] = useState("");
  const [profileError, setProfileError] = useState("");

  // ── Password ──────────────────────────────────────────────────────────────
  const [pwForm, setPwForm] = useState({ current_password: "", new_password: "", confirm: "" });
  const [pwSuccess, setPwSuccess] = useState("");
  const [pwError, setPwError] = useState("");

  // ── Config ────────────────────────────────────────────────────────────────
  const [trimming, setTrimming] = useState<TrimmingConfig>(DEFAULT_TRIMMING);
  const [transcription, setTranscription] = useState<TranscriptionConfig>(DEFAULT_TRANSCRIPTION);
  const [download, setDownload] = useState<DownloadConfig>(DEFAULT_DOWNLOAD);
  const [upload, setUpload] = useState<UploadConfig>(DEFAULT_UPLOAD);
  const [metadata, setMetadata] = useState<MetadataConfig>(DEFAULT_METADATA);
  const [retention, setRetention] = useState<RetentionConfig>(DEFAULT_RETENTION);
  const [configSuccess, setConfigSuccess] = useState("");
  const [configError, setConfigError] = useState("");

  // ── Collapsible open states ───────────────────────────────────────────────
  const [transcriptionAdvOpen, setTranscriptionAdvOpen] = useState(false);
  const [trimmingAdvOpen, setTrimmingAdvOpen] = useState(false);
  const [downloadOpen, setDownloadOpen] = useState(false);
  const [metadataOpen, setMetadataOpen] = useState(false);
  const [retentionOpen, setRetentionOpen] = useState(false);

  // ── Reset confirmation ────────────────────────────────────────────────────
  const [resetConfirm, setResetConfirm] = useState(false);

  // ── Danger Zone ───────────────────────────────────────────────────────────
  const [deleteAccountOpen, setDeleteAccountOpen] = useState(false);
  const [deleteAccountPassword, setDeleteAccountPassword] = useState("");
  const [deleteAccountError, setDeleteAccountError] = useState("");
  const [logoutAllSuccess, setLogoutAllSuccess] = useState(false);

  // ── Reference data ───────────────────────────────────────────────────────
  const { data: languages = [] } = useLanguages();
  const { data: granularities = [] } = useGranularities();
  const { data: qualities = [] } = useQualities();
  const { data: timezones = [] } = useTimezones();

  // ── Queries ───────────────────────────────────────────────────────────────
  const { data: userData } = useQuery<UserMe>({
    queryKey: ["user-me"],
    queryFn: async () => (await apiClient.get<UserMe>("/users/me")).data,
  });

  const { data: configData } = useQuery<UserConfig>({
    queryKey: ["user-config"],
    queryFn: async () => (await apiClient.get<UserConfig>("/users/me/config")).data,
  });

  const { data: quotaData } = useQuery<QuotaStatus>({
    queryKey: ["user-quota"],
    queryFn: async () => (await apiClient.get<QuotaStatus>("/users/me/quota")).data,
  });

  const { data: statsData } = useQuery<UserStats>({
    queryKey: ["user-stats"],
    queryFn: async () => (await apiClient.get<UserStats>("/users/me/stats")).data,
  });

  // ── Sync from server ──────────────────────────────────────────────────────
  useEffect(() => {
    if (!userData) return;
    setProfile({
      full_name: userData.full_name ?? "",
      email: userData.email,
      timezone: userData.timezone,
    });
  }, [userData]);

  useEffect(() => {
    if (!configData?.config_data) return;
    const { trimming: t, transcription: tr, download: d, upload: u, metadata: m, retention: r } =
      configData.config_data;
    if (t) setTrimming({ ...DEFAULT_TRIMMING, ...t });
    if (tr) setTranscription({ ...DEFAULT_TRANSCRIPTION, ...tr });
    if (d) setDownload({ ...DEFAULT_DOWNLOAD, ...d });
    if (u) setUpload({ ...DEFAULT_UPLOAD, ...u });
    if (m) setMetadata({ ...DEFAULT_METADATA, ...m });
    if (r) setRetention({ ...DEFAULT_RETENTION, ...r });
  }, [configData]);

  // ── Mutations ─────────────────────────────────────────────────────────────
  const updateProfile = useMutation({
    mutationFn: () =>
      apiClient.patch("/users/me", {
        full_name: profile.full_name,
        timezone: profile.timezone,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["user-me"] });
      setProfileSuccess("Saved!");
      setProfileError("");
      setTimeout(() => setProfileSuccess(""), TOAST_SHORT);
    },
    onError: (err) => setProfileError(extractError(err)),
  });

  const changePassword = useMutation({
    mutationFn: () =>
      apiClient.post("/users/me/password", {
        current_password: pwForm.current_password,
        new_password: pwForm.new_password,
      }),
    onSuccess: () => {
      setPwSuccess("Password changed. All sessions terminated.");
      setPwError("");
      setPwForm({ current_password: "", new_password: "", confirm: "" });
      setTimeout(() => setPwSuccess(""), TOAST_LONG);
    },
    onError: (err) => setPwError(extractError(err)),
  });

  const updateConfig = useMutation({
    mutationFn: () =>
      apiClient.patch("/users/me/config", {
        trimming,
        transcription,
        download,
        upload,
        metadata,
        retention,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["user-config"] });
      setConfigSuccess("Saved!");
      setConfigError("");
      setTimeout(() => setConfigSuccess(""), TOAST_SHORT);
    },
    onError: (err) => setConfigError(extractError(err)),
  });

  const resetConfig = useMutation({
    mutationFn: () => apiClient.post("/users/me/config/reset"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["user-config"] });
      setConfigSuccess("Reset to defaults.");
      setResetConfirm(false);
      setTimeout(() => setConfigSuccess(""), TOAST_SHORT);
    },
  });

  const logoutAll = useMutation({
    mutationFn: () => apiClient.post("/auth/logout-all"),
    onSuccess: () => {
      setLogoutAllSuccess(true);
      setTimeout(() => setLogoutAllSuccess(false), TOAST_LONG);
    },
  });

  const deleteAccount = useMutation({
    mutationFn: () => apiClient.delete("/users/me", { data: { password: deleteAccountPassword } }),
    onSuccess: () => {
      qc.clear();
      router.push("/login");
    },
    onError: (err) => setDeleteAccountError(extractError(err)),
  });

  // ── Password submit ───────────────────────────────────────────────────────
  function handlePasswordSubmit() {
    if (!pwForm.current_password) { setPwError("Enter current password"); return; }
    if (pwForm.new_password !== pwForm.confirm) { setPwError("Passwords don't match"); return; }
    if (pwForm.new_password.length < 8) { setPwError("Min 8 characters"); return; }
    if (!/\d/.test(pwForm.new_password)) { setPwError("Must include a digit"); return; }
    if (!/[A-Z]/.test(pwForm.new_password)) { setPwError("Must include an uppercase letter"); return; }
    setPwError("");
    changePassword.mutate();
  }

  // ── Quota helpers ─────────────────────────────────────────────────────────
  const q = quotaData;
  const planName = q?.subscription?.plan?.display_name ?? null;
  const recUsed = q?.recordings?.used ?? 0;
  const recLimit = q?.recordings?.limit ?? null;
  const stUsedGb = q?.storage?.used_gb ?? 0;
  const stLimitGb = q?.storage?.limit_gb ?? null;
  const ctUsed = q?.concurrent_tasks?.used ?? 0;
  const ctLimit = q?.concurrent_tasks?.limit ?? null;
  const ajUsed = q?.automation_jobs?.used ?? 0;
  const ajLimit = q?.automation_jobs?.limit ?? null;

  // Stats helpers
  const s = statsData;
  const transcribedMin = s ? Math.floor(s.transcription_total_seconds / 60) : 0;
  const statusEntries = s
    ? Object.entries(s.recordings_by_status).filter(([, v]) => v > 0)
    : [];

  return (
    <div className="w-full min-w-0 p-6 sm:p-8 space-y-6">
      <h1 className="text-xl font-semibold text-gray-900">Settings</h1>

      {/* ── Usage & Quota ────────────────────────────────────────────────── */}
      {(quotaData || statsData) && (
        <div className="bg-white rounded-2xl border border-[#D9D9D9] shadow-sm p-6">
          <div className="flex items-center justify-between mb-5">
            <h2 className="text-sm font-semibold text-gray-900">Usage &amp; Quota</h2>
            {planName && (
              <span className="text-xs font-medium text-[#224C87] bg-[#224C87]/8 px-2.5 py-1 rounded-full">
                {planName}
              </span>
            )}
          </div>

          {quotaData && (
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-x-8 gap-y-4">
              <QuotaBar label="Recordings / month" used={recUsed} limit={recLimit} />
              <QuotaBar label="Storage" used={stUsedGb} limit={stLimitGb} suffix=" GB" />
              <QuotaBar label="Concurrent tasks" used={ctUsed} limit={ctLimit} />
              <QuotaBar label="Automation jobs" used={ajUsed} limit={ajLimit} />
            </div>
          )}

          {statsData && (
            <div className="mt-5 pt-5 border-t border-[#F0F0F0]">
              <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-x-6 gap-y-4">
                <StatChip label="Total recordings" value={s!.recordings_total} />
                <StatChip label="Storage used" value={`${s!.storage_gb.toFixed(2)} GB`} />
                <StatChip label="Transcribed" value={`${transcribedMin} min`} />
                {statusEntries.map(([status, count]) => (
                  <StatChip key={status} label={status} value={count} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Profile ──────────────────────────────────────────────────────── */}
      <SectionCard title="Profile">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <Field label="Full name">
            <input
              type="text"
              value={profile.full_name}
              onChange={(e) => setProfile((p) => ({ ...p, full_name: e.target.value }))}
              placeholder="Your name"
              className={FILTER_CONTROL}
            />
          </Field>
          <Field label="Email">
            <input
              type="email"
              value={profile.email}
              disabled
              className={cn(FILTER_CONTROL, "bg-gray-50 text-gray-400 cursor-not-allowed")}
            />
          </Field>
        </div>
        <Field label="Timezone">
          <select
            value={timezones.some((t) => t.value === profile.timezone) ? profile.timezone : "__custom__"}
            onChange={(e) => {
              if (e.target.value !== "__custom__") {
                setProfile((p) => ({ ...p, timezone: e.target.value }));
              }
            }}
            className={cn(FILTER_CONTROL, "max-w-sm")}
          >
            {timezones.map((tz) => (
              <option key={tz.value} value={tz.value}>{tz.label}</option>
            ))}
            {!timezones.some((t) => t.value === profile.timezone) && profile.timezone && (
              <option value="__custom__">{profile.timezone} (custom)</option>
            )}
          </select>
        </Field>
        {profileError && (
          <p className="text-sm text-red-500 bg-red-50 px-3 py-2 rounded-xl">{profileError}</p>
        )}
        {profileSuccess && (
          <p className="text-sm text-green-600 bg-green-50 px-3 py-2 rounded-xl">{profileSuccess}</p>
        )}
        <div className="flex justify-end">
          <button
            onClick={() => updateProfile.mutate()}
            disabled={updateProfile.isPending}
            className={BTN_PRIMARY}
          >
            <Save size={15} />
            {updateProfile.isPending ? "Saving…" : "Save profile"}
          </button>
        </div>
      </SectionCard>

      {/* ── Change password ───────────────────────────────────────────────── */}
      <SectionCard title="Change password">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
          <Field label="Current password">
            <input
              type="password"
              value={pwForm.current_password}
              onChange={(e) => setPwForm((p) => ({ ...p, current_password: e.target.value }))}
              placeholder="••••••••"
              className={FILTER_CONTROL}
            />
          </Field>
          <Field label="New password">
            <input
              type="password"
              value={pwForm.new_password}
              onChange={(e) => setPwForm((p) => ({ ...p, new_password: e.target.value }))}
              placeholder="Min 8 chars, 1 digit, 1 uppercase"
              className={FILTER_CONTROL}
            />
          </Field>
          <Field label="Confirm new password">
            <input
              type="password"
              value={pwForm.confirm}
              onChange={(e) => setPwForm((p) => ({ ...p, confirm: e.target.value }))}
              placeholder="Repeat"
              className={FILTER_CONTROL}
            />
          </Field>
        </div>
        {pwError && (
          <p className="text-sm text-red-500 bg-red-50 px-3 py-2 rounded-xl">{pwError}</p>
        )}
        {pwSuccess && (
          <p className="text-sm text-green-600 bg-green-50 px-3 py-2 rounded-xl">{pwSuccess}</p>
        )}
        <div className="flex justify-end">
          <button
            onClick={handlePasswordSubmit}
            disabled={changePassword.isPending}
            className={BTN_PRIMARY}
          >
            <Save size={15} />
            {changePassword.isPending ? "Changing…" : "Change password"}
          </button>
        </div>
      </SectionCard>

      {/* ── Processing defaults ───────────────────────────────────────────── */}
      <SectionCard
        title="Processing defaults"
        action={
          resetConfirm ? (
            <div className="flex items-center gap-2">
              <span className="text-xs text-amber-600 hidden sm:inline">Reset all to defaults?</span>
              <button
                onClick={() => resetConfig.mutate()}
                disabled={resetConfig.isPending}
                className="text-xs font-medium text-red-600 hover:text-red-700 px-2 py-1 rounded-lg hover:bg-red-50 transition-colors disabled:opacity-50"
              >
                {resetConfig.isPending ? "Resetting…" : "Yes, reset"}
              </button>
              <button
                onClick={() => setResetConfirm(false)}
                className="text-xs font-medium text-gray-500 hover:text-gray-700 px-2 py-1 rounded-lg hover:bg-gray-100 transition-colors"
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              onClick={() => setResetConfirm(true)}
              className={cn(BTN_SECONDARY, "text-xs gap-1.5 px-3 py-1.5")}
            >
              <RefreshCw size={12} />
              Reset
            </button>
          )
        }
      >
        {/* Main toggles — visible immediately */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-10 gap-y-0.5">
          <Toggle
            label="Enable transcription"
            hint="ASR via Fireworks/Whisper"
            checked={transcription.enable_transcription}
            onChange={(v) => setTranscription((c) => ({ ...c, enable_transcription: v }))}
          />
          <Toggle
            label="Extract topics"
            hint="DeepSeek topic extraction"
            checked={transcription.enable_topics}
            onChange={(v) => setTranscription((c) => ({ ...c, enable_topics: v }))}
          />
          <Toggle
            label="Generate subtitles"
            hint="Creates SRT/VTT alongside the video"
            checked={transcription.enable_subtitles}
            onChange={(v) => setTranscription((c) => ({ ...c, enable_subtitles: v }))}
          />
          <Toggle
            label="Enable trimming"
            hint="Auto-trim silence from start/end"
            checked={trimming.enable_trimming}
            onChange={(v) => setTrimming((c) => ({ ...c, enable_trimming: v }))}
          />
          <Toggle
            label="Auto-upload"
            hint="Upload immediately after processing"
            checked={upload.auto_upload}
            onChange={(v) => setUpload((c) => ({ ...c, auto_upload: v }))}
          />
          <Toggle
            label="Upload captions"
            hint="Include SRT/VTT when uploading"
            checked={upload.upload_captions}
            onChange={(v) => setUpload((c) => ({ ...c, upload_captions: v }))}
          />
        </div>

        {/* Language + granularity */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <Field label="Transcription language">
            <div className={FILTER_SEGMENT_WRAP}>
              {languages.map(({ value, label }) => (
                <button
                  key={value}
                  type="button"
                  className={cn(
                    FILTER_SEGMENT_BTN,
                    transcription.language === value ? FILTER_SEGMENT_ACTIVE : FILTER_SEGMENT_IDLE
                  )}
                  onClick={() => setTranscription((c) => ({ ...c, language: value }))}
                >
                  {label}
                </button>
              ))}
            </div>
          </Field>
          <Field label="Topic granularity">
            <div className={FILTER_SEGMENT_WRAP}>
              {granularities.map(({ value, label }) => (
                <button
                  key={value}
                  type="button"
                  className={cn(
                    FILTER_SEGMENT_BTN,
                    transcription.granularity === value ? FILTER_SEGMENT_ACTIVE : FILTER_SEGMENT_IDLE
                  )}
                  onClick={() => setTranscription((c) => ({ ...c, granularity: value }))}
                >
                  {label}
                </button>
              ))}
            </div>
          </Field>
        </div>

        {/* Advanced transcription */}
        <Collapsible
          label="Advanced transcription"
          open={transcriptionAdvOpen}
          onToggle={() => setTranscriptionAdvOpen((v) => !v)}
        >
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
            <Field label="Questions per recording" hint="Self-check questions (1–10)">
              <input
                type="number"
                min={1}
                max={10}
                value={transcription.questions_count}
                onChange={(e) =>
                  setTranscription((c) => ({
                    ...c,
                    questions_count: Math.max(1, Math.min(10, parseInt(e.target.value) || 1)),
                  }))
                }
                className={cn(FILTER_CONTROL, "max-w-[8rem]")}
              />
            </Field>
            <div className="space-y-0.5">
              <Toggle
                label="Allow transcription errors"
                hint="Continue if ASR returns partial errors"
                checked={transcription.allow_errors}
                onChange={(v) => setTranscription((c) => ({ ...c, allow_errors: v }))}
              />
              <Toggle
                label="Enable translation"
                hint="Translate transcript after ASR"
                checked={transcription.enable_translation}
                onChange={(v) => setTranscription((c) => ({ ...c, enable_translation: v }))}
              />
            </div>
          </div>

          {transcription.enable_translation && (
            <Field label="Translation language" hint="BCP-47 code, e.g. en, de, fr">
              <input
                type="text"
                value={transcription.translation_language}
                onChange={(e) =>
                  setTranscription((c) => ({ ...c, translation_language: e.target.value }))
                }
                placeholder="en"
                className={cn(FILTER_CONTROL, "max-w-[8rem]")}
              />
            </Field>
          )}

          <Field label="Transcription prompt" hint="Context hint for the ASR model (not a system prompt)">
            <textarea
              value={transcription.prompt}
              onChange={(e) => setTranscription((c) => ({ ...c, prompt: e.target.value }))}
              rows={3}
              placeholder="University lecture: machine learning, neural networks…"
              className={cn(FILTER_CONTROL, "resize-y font-mono text-xs")}
            />
          </Field>

          <Field label="Vocabulary" hint="Key terms that improve recognition accuracy">
            <TagInput
              tags={transcription.vocabulary}
              onChange={(v) => setTranscription((c) => ({ ...c, vocabulary: v }))}
              placeholder="Add term…"
            />
          </Field>
        </Collapsible>

        {/* Advanced trimming */}
        <Collapsible
          label="Advanced trimming"
          open={trimmingAdvOpen}
          onToggle={() => setTrimmingAdvOpen((v) => !v)}
        >
          <Toggle
            label="Audio detection mode"
            hint="Detect audio energy rather than simple silence"
            checked={trimming.audio_detection}
            onChange={(v) => setTrimming((c) => ({ ...c, audio_detection: v }))}
          />
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <Field label="Silence threshold (dB)">
              <input
                type="number"
                step={1}
                min={-100}
                max={0}
                value={trimming.silence_threshold}
                onChange={(e) =>
                  setTrimming((c) => ({ ...c, silence_threshold: parseFloat(e.target.value) || -40 }))
                }
                className={FILTER_CONTROL}
              />
            </Field>
            <Field label="Min silence (s)">
              <input
                type="number"
                step={0.5}
                min={0}
                value={trimming.min_silence_duration}
                onChange={(e) =>
                  setTrimming((c) => ({
                    ...c,
                    min_silence_duration: parseFloat(e.target.value) || 0,
                  }))
                }
                className={FILTER_CONTROL}
              />
            </Field>
            <Field label="Padding before (s)">
              <input
                type="number"
                step={0.5}
                min={0}
                value={trimming.padding_before}
                onChange={(e) =>
                  setTrimming((c) => ({ ...c, padding_before: parseFloat(e.target.value) || 0 }))
                }
                className={FILTER_CONTROL}
              />
            </Field>
            <Field label="Padding after (s)">
              <input
                type="number"
                step={0.5}
                min={0}
                value={trimming.padding_after}
                onChange={(e) =>
                  setTrimming((c) => ({ ...c, padding_after: parseFloat(e.target.value) || 0 }))
                }
                className={FILTER_CONTROL}
              />
            </Field>
          </div>
        </Collapsible>

        {/* Download settings */}
        <Collapsible
          label="Download settings"
          open={downloadOpen}
          onToggle={() => setDownloadOpen((v) => !v)}
        >
          <Toggle
            label="Auto-download"
            hint="Automatically download new recordings from connected sources"
            checked={download.auto_download}
            onChange={(v) => setDownload((c) => ({ ...c, auto_download: v }))}
          />
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
            <Field label="Video quality">
              <div className={FILTER_SEGMENT_WRAP}>
                {qualities.map(({ value, label }) => (
                  <button
                    key={value}
                    type="button"
                    className={cn(
                      FILTER_SEGMENT_BTN,
                      download.quality === value ? FILTER_SEGMENT_ACTIVE : FILTER_SEGMENT_IDLE
                    )}
                    onClick={() => setDownload((c) => ({ ...c, quality: value }))}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </Field>
            <Field label="Max file size (MB)">
              <input
                type="number"
                min={1}
                value={download.max_file_size_mb}
                onChange={(e) =>
                  setDownload((c) => ({ ...c, max_file_size_mb: parseInt(e.target.value) || 1 }))
                }
                className={cn(FILTER_CONTROL, "max-w-[10rem]")}
              />
            </Field>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <Field label="Retry attempts (0–10)">
              <input
                type="number"
                min={0}
                max={10}
                value={download.retry_attempts}
                onChange={(e) =>
                  setDownload((c) => ({
                    ...c,
                    retry_attempts: Math.max(0, Math.min(10, parseInt(e.target.value) || 0)),
                  }))
                }
                className={FILTER_CONTROL}
              />
            </Field>
            <Field label="Retry delay (s)">
              <input
                type="number"
                min={0}
                value={download.retry_delay}
                onChange={(e) =>
                  setDownload((c) => ({ ...c, retry_delay: parseInt(e.target.value) || 0 }))
                }
                className={FILTER_CONTROL}
              />
            </Field>
          </div>
        </Collapsible>

        {/* Metadata defaults */}
        <Collapsible
          label="Metadata defaults"
          open={metadataOpen}
          onToggle={() => setMetadataOpen((v) => !v)}
        >
          <TemplateField
            label="Title template"
            value={metadata.title_template}
            onChange={(v) => setMetadata((c) => ({ ...c, title_template: v }))}
            placeholder="{{ display_name }} | {{ topic }} ({{ date }})"
          />
          <TemplateField
            label="Description template"
            value={metadata.description_template}
            onChange={(v) => setMetadata((c) => ({ ...c, description_template: v }))}
            multiline
            placeholder={"Recording from {{ date }}\n\n{{ topics }}"}
          />
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
            <Field label="Date format" hint="e.g. DD.MM.YYYY or YYYY-MM-DD">
              <input
                type="text"
                value={metadata.date_format}
                onChange={(e) => setMetadata((c) => ({ ...c, date_format: e.target.value }))}
                placeholder="DD.MM.YYYY"
                className={cn(FILTER_CONTROL, "max-w-[14rem] font-mono text-xs")}
              />
            </Field>
            <Field label="Default tags">
              <TagInput
                tags={metadata.tags}
                onChange={(v) => setMetadata((c) => ({ ...c, tags: v }))}
                placeholder="Add tag…"
              />
            </Field>
          </div>
        </Collapsible>

        {/* Retention */}
        <Collapsible
          label="Retention"
          open={retentionOpen}
          onToggle={() => setRetentionOpen((v) => !v)}
        >
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
            <Field label="Soft delete (days)" hint="Move to trash after N days of inactivity">
              <input
                type="number"
                min={1}
                value={retention.soft_delete_days}
                onChange={(e) =>
                  setRetention((c) => ({ ...c, soft_delete_days: Math.max(1, parseInt(e.target.value) || 1) }))
                }
                className={FILTER_CONTROL}
              />
            </Field>
            <Field label="Hard delete (days)" hint="Permanently delete N days after soft-delete">
              <input
                type="number"
                min={1}
                value={retention.hard_delete_days}
                onChange={(e) =>
                  setRetention((c) => ({ ...c, hard_delete_days: Math.max(1, parseInt(e.target.value) || 1) }))
                }
                className={FILTER_CONTROL}
              />
            </Field>
            <Field label="Auto-expire (days)" hint="Archive after N days of no activity">
              <input
                type="number"
                min={1}
                value={retention.auto_expire_days}
                onChange={(e) =>
                  setRetention((c) => ({ ...c, auto_expire_days: Math.max(1, parseInt(e.target.value) || 1) }))
                }
                className={FILTER_CONTROL}
              />
            </Field>
          </div>
        </Collapsible>

        {configError && (
          <p className="text-sm text-red-500 bg-red-50 px-3 py-2 rounded-xl">{configError}</p>
        )}
        {configSuccess && (
          <p className="text-sm text-green-600 bg-green-50 px-3 py-2 rounded-xl">{configSuccess}</p>
        )}

        <div className="flex justify-end">
          <button
            onClick={() => updateConfig.mutate()}
            disabled={updateConfig.isPending}
            className={BTN_PRIMARY}
          >
            <Save size={15} />
            {updateConfig.isPending ? "Saving…" : "Save settings"}
          </button>
        </div>
      </SectionCard>

      {/* ── Danger Zone ─────────────────────────────────────────────────────── */}
      <div className="rounded-2xl border border-red-200 bg-white shadow-sm">
        <div className="px-6 py-4 border-b border-red-100">
          <h2 className="text-sm font-semibold text-red-600">Danger Zone</h2>
        </div>
        <div className="p-6 space-y-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-sm font-medium text-gray-800">Log out all devices</p>
              <p className="text-xs text-gray-400 mt-0.5">Invalidates all active sessions. You will need to log in again on each device.</p>
            </div>
            <button
              type="button"
              onClick={() => logoutAll.mutate()}
              disabled={logoutAll.isPending}
              className="shrink-0 flex items-center gap-2 rounded-xl border border-[#D9D9D9] bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-50"
            >
              <LogOut size={14} />
              {logoutAll.isPending ? "Logging out…" : "Log out all"}
            </button>
          </div>
          {logoutAllSuccess && (
            <p className="text-sm text-green-600 bg-green-50 rounded-xl px-3 py-2">All sessions terminated.</p>
          )}

          <div className="border-t border-[#F0F0F0] pt-4 flex items-start justify-between gap-4">
            <div>
              <p className="text-sm font-medium text-gray-800">Delete account</p>
              <p className="text-xs text-gray-400 mt-0.5">Permanently delete your account and all data. This cannot be undone.</p>
            </div>
            <button
              type="button"
              onClick={() => { setDeleteAccountPassword(""); setDeleteAccountError(""); setDeleteAccountOpen(true); }}
              className="shrink-0 flex items-center gap-2 rounded-xl border border-red-200 bg-white px-4 py-2 text-sm font-medium text-red-500 transition-colors hover:bg-red-50"
            >
              <Trash2 size={14} />
              Delete account
            </button>
          </div>
        </div>
      </div>

      {/* Delete account modal */}
      {deleteAccountOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
          onClick={(e) => { if (e.currentTarget === e.target) setDeleteAccountOpen(false); }}
        >
          <div className="w-full max-w-sm rounded-2xl bg-white p-6 shadow-xl">
            <h2 className="mb-1 text-sm font-semibold text-gray-900">Delete your account?</h2>
            <p className="mb-4 text-xs text-gray-500">This is permanent and irreversible. Enter your password to confirm.</p>
            <div className="space-y-3">
              <input
                type="password"
                autoFocus
                value={deleteAccountPassword}
                onChange={(e) => setDeleteAccountPassword(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && deleteAccountPassword) deleteAccount.mutate();
                  if (e.key === "Escape") setDeleteAccountOpen(false);
                }}
                placeholder="Your password"
                className="w-full rounded-xl border border-[#D9D9D9] px-3 py-2 text-sm outline-none focus:border-red-400 focus:ring-1 focus:ring-red-200"
              />
              {deleteAccountError && (
                <p className="text-xs text-red-500">{deleteAccountError}</p>
              )}
              <div className="flex justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => setDeleteAccountOpen(false)}
                  className="rounded-xl border border-[#D9D9D9] px-4 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={!deleteAccountPassword || deleteAccount.isPending}
                  onClick={() => deleteAccount.mutate()}
                  className="flex items-center gap-1.5 rounded-xl bg-red-500 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-red-600 disabled:opacity-50"
                >
                  {deleteAccount.isPending ? <RefreshCw size={13} className="animate-spin" /> : <Trash2 size={13} />}
                  Delete permanently
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
