"use client";

import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Save, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/api/client";

interface UserMe {
  id: string;
  email: string;
  full_name: string | null;
  timezone: string;
  role: string;
  created_at: string;
}

interface UserConfig {
  config_data: {
    transcription: {
      enable_transcription: boolean;
      language: string;
      enable_topics: boolean;
      granularity: string;
      enable_subtitles: boolean;
    };
    trimming: {
      enable_trimming: boolean;
    };
    upload: {
      auto_upload: boolean;
    };
  };
}

const LANGUAGES = [
  { value: "ru", label: "Russian" },
  { value: "en", label: "English" },
  { value: "auto", label: "Auto-detect" },
];

const GRANULARITY_OPTIONS = [
  { value: "short", label: "Short (fewer, longer topics)" },
  { value: "medium", label: "Medium" },
  { value: "long", label: "Long (more, shorter topics)" },
];

const inp = "w-full px-4 py-2.5 rounded-xl border border-[#D9D9D9] text-sm outline-none focus:border-[#224C87] focus:ring-2 focus:ring-[#224C87]/10 transition-colors";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-2xl border border-[#D9D9D9] shadow-sm p-6 space-y-5">
      <h2 className="text-sm font-semibold text-gray-700 pb-2 border-b border-[#D9D9D9]">{title}</h2>
      {children}
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1.5">{label}</label>
      {hint && <p className="text-xs text-gray-400 mb-1.5">{hint}</p>}
      {children}
    </div>
  );
}

function Toggle({ label, hint, checked, onChange }: { label: string; hint?: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="flex items-center justify-between py-1">
      <div>
        <p className="text-sm font-medium text-gray-700">{label}</p>
        {hint && <p className="text-xs text-gray-400">{hint}</p>}
      </div>
      <button type="button" onClick={() => onChange(!checked)} className={cn("relative inline-flex h-6 w-11 items-center rounded-full transition-colors ml-4", checked ? "bg-[#224C87]" : "bg-gray-200")}>
        <span className={cn("inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform", checked ? "translate-x-6" : "translate-x-1")} />
      </button>
    </div>
  );
}

export default function SettingsPage() {
  const qc = useQueryClient();

  // Profile
  const [profile, setProfile] = useState({ full_name: "", email: "", timezone: "" });
  const [profileSuccess, setProfileSuccess] = useState("");
  const [profileError, setProfileError] = useState("");

  // Password
  const [pwForm, setPwForm] = useState({ current_password: "", new_password: "", confirm: "" });
  const [pwSuccess, setPwSuccess] = useState("");
  const [pwError, setPwError] = useState("");

  // Config
  const [config, setConfig] = useState({
    enable_transcription: true,
    language: "ru",
    enable_topics: true,
    granularity: "medium",
    enable_subtitles: true,
    enable_trimming: true,
    auto_upload: false,
  });
  const [configSuccess, setConfigSuccess] = useState("");
  const [configError, setConfigError] = useState("");

  const { data: userData } = useQuery<UserMe>({
    queryKey: ["user-me"],
    queryFn: async () => {
      const res = await apiClient.get<UserMe>("/users/me");
      return res.data;
    },
  });

  const { data: configData } = useQuery<UserConfig>({
    queryKey: ["user-config"],
    queryFn: async () => {
      const res = await apiClient.get<UserConfig>("/users/me/config");
      return res.data;
    },
  });

  useEffect(() => {
    if (!userData) return;
    setProfile({ full_name: userData.full_name ?? "", email: userData.email, timezone: userData.timezone });
  }, [userData]);

  useEffect(() => {
    if (!configData?.config_data) return;
    const { transcription, trimming, upload } = configData.config_data;
    setConfig({
      enable_transcription: transcription.enable_transcription,
      language: transcription.language,
      enable_topics: transcription.enable_topics,
      granularity: transcription.granularity,
      enable_subtitles: transcription.enable_subtitles,
      enable_trimming: trimming.enable_trimming,
      auto_upload: upload.auto_upload,
    });
  }, [configData]);

  const updateProfile = useMutation({
    mutationFn: () => apiClient.patch("/users/me", { full_name: profile.full_name, timezone: profile.timezone }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["user-me"] });
      setProfileSuccess("Profile updated!");
      setProfileError("");
      setTimeout(() => setProfileSuccess(""), 3000);
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setProfileError(typeof msg === "string" ? msg : "Failed to update profile");
    },
  });

  const changePassword = useMutation({
    mutationFn: () => apiClient.post("/users/me/password", {
      current_password: pwForm.current_password,
      new_password: pwForm.new_password,
    }),
    onSuccess: () => {
      setPwSuccess("Password changed successfully!");
      setPwError("");
      setPwForm({ current_password: "", new_password: "", confirm: "" });
      setTimeout(() => setPwSuccess(""), 4000);
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setPwError(typeof msg === "string" ? msg : "Failed to change password");
    },
  });

  const updateConfig = useMutation({
    mutationFn: () => apiClient.patch("/users/me/config", {
      transcription: {
        enable_transcription: config.enable_transcription,
        language: config.language,
        enable_topics: config.enable_topics,
        granularity: config.granularity,
        enable_subtitles: config.enable_subtitles,
      },
      trimming: { enable_trimming: config.enable_trimming },
      upload: { auto_upload: config.auto_upload },
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["user-config"] });
      setConfigSuccess("Settings saved!");
      setConfigError("");
      setTimeout(() => setConfigSuccess(""), 3000);
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setConfigError(typeof msg === "string" ? msg : "Failed to save settings");
    },
  });

  const resetConfig = useMutation({
    mutationFn: () => apiClient.post("/users/me/config/reset"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["user-config"] });
      setConfigSuccess("Reset to defaults!");
      setTimeout(() => setConfigSuccess(""), 3000);
    },
  });

  function handlePasswordSubmit() {
    if (!pwForm.current_password) { setPwError("Enter current password"); return; }
    if (pwForm.new_password !== pwForm.confirm) { setPwError("New passwords don't match"); return; }
    if (pwForm.new_password.length < 8) { setPwError("Password must be at least 8 characters"); return; }
    if (!/\d/.test(pwForm.new_password)) { setPwError("Password must contain at least one digit"); return; }
    if (!/[A-Z]/.test(pwForm.new_password)) { setPwError("Password must contain at least one uppercase letter"); return; }
    setPwError("");
    changePassword.mutate();
  }

  return (
    <div className="p-8 max-w-2xl space-y-6">
      <h1 className="text-xl font-semibold text-gray-900">Settings</h1>

      {/* Profile section */}
      <Section title="Profile">
        <Field label="Full name">
          <input
            type="text"
            value={profile.full_name}
            onChange={(e) => setProfile((p) => ({ ...p, full_name: e.target.value }))}
            placeholder="Your name"
            className={inp}
          />
        </Field>
        <Field label="Email">
          <input
            type="email"
            value={profile.email}
            disabled
            className={cn(inp, "bg-gray-50 text-gray-400 cursor-not-allowed")}
          />
        </Field>
        <Field label="Timezone" hint="IANA timezone (e.g. Europe/Moscow)">
          <input
            type="text"
            value={profile.timezone}
            onChange={(e) => setProfile((p) => ({ ...p, timezone: e.target.value }))}
            placeholder="Europe/Moscow"
            className={inp}
          />
        </Field>
        {profileError && <p className="text-sm text-red-500 bg-red-50 px-3 py-2 rounded-xl">{profileError}</p>}
        {profileSuccess && <p className="text-sm text-green-600 bg-green-50 px-3 py-2 rounded-xl">{profileSuccess}</p>}
        <div className="flex justify-end">
          <button
            onClick={() => updateProfile.mutate()}
            disabled={updateProfile.isPending}
            className="flex items-center gap-2 bg-[#224C87] text-white px-4 py-2 rounded-xl text-sm font-medium hover:bg-[#1a3d6e] disabled:opacity-50 transition-colors"
          >
            <Save size={15} />
            {updateProfile.isPending ? "Saving…" : "Save profile"}
          </button>
        </div>
      </Section>

      {/* Password section */}
      <Section title="Change password">
        <Field label="Current password">
          <input
            type="password"
            value={pwForm.current_password}
            onChange={(e) => setPwForm((p) => ({ ...p, current_password: e.target.value }))}
            placeholder="••••••••"
            className={inp}
          />
        </Field>
        <Field label="New password">
          <input
            type="password"
            value={pwForm.new_password}
            onChange={(e) => setPwForm((p) => ({ ...p, new_password: e.target.value }))}
            placeholder="Min. 8 chars, 1 digit, 1 uppercase"
            className={inp}
          />
        </Field>
        <Field label="Confirm new password">
          <input
            type="password"
            value={pwForm.confirm}
            onChange={(e) => setPwForm((p) => ({ ...p, confirm: e.target.value }))}
            placeholder="Repeat new password"
            className={inp}
          />
        </Field>
        {pwError && <p className="text-sm text-red-500 bg-red-50 px-3 py-2 rounded-xl">{pwError}</p>}
        {pwSuccess && <p className="text-sm text-green-600 bg-green-50 px-3 py-2 rounded-xl">{pwSuccess}</p>}
        <div className="flex justify-end">
          <button
            onClick={handlePasswordSubmit}
            disabled={changePassword.isPending}
            className="flex items-center gap-2 bg-[#224C87] text-white px-4 py-2 rounded-xl text-sm font-medium hover:bg-[#1a3d6e] disabled:opacity-50 transition-colors"
          >
            <Save size={15} />
            {changePassword.isPending ? "Changing…" : "Change password"}
          </button>
        </div>
      </Section>

      {/* Processing defaults */}
      <Section title="Processing defaults">
        <Toggle label="Enable transcription" checked={config.enable_transcription} onChange={(v) => setConfig((c) => ({ ...c, enable_transcription: v }))} />
        <Toggle label="Extract topics" checked={config.enable_topics} onChange={(v) => setConfig((c) => ({ ...c, enable_topics: v }))} />
        <Toggle label="Generate subtitles" checked={config.enable_subtitles} onChange={(v) => setConfig((c) => ({ ...c, enable_subtitles: v }))} />
        <Toggle label="Enable trimming" hint="Auto-trim silence from start/end" checked={config.enable_trimming} onChange={(v) => setConfig((c) => ({ ...c, enable_trimming: v }))} />
        <Toggle label="Auto-upload after processing" checked={config.auto_upload} onChange={(v) => setConfig((c) => ({ ...c, auto_upload: v }))} />

        <Field label="Default language">
          <select value={config.language} onChange={(e) => setConfig((c) => ({ ...c, language: e.target.value }))} className={cn(inp, "bg-white")}>
            {LANGUAGES.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
          </select>
        </Field>
        <Field label="Topic granularity">
          <select value={config.granularity} onChange={(e) => setConfig((c) => ({ ...c, granularity: e.target.value }))} className={cn(inp, "bg-white")}>
            {GRANULARITY_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </Field>

        {configError && <p className="text-sm text-red-500 bg-red-50 px-3 py-2 rounded-xl">{configError}</p>}
        {configSuccess && <p className="text-sm text-green-600 bg-green-50 px-3 py-2 rounded-xl">{configSuccess}</p>}

        <div className="flex items-center justify-between">
          <button
            onClick={() => resetConfig.mutate()}
            disabled={resetConfig.isPending}
            className="flex items-center gap-2 px-4 py-2 rounded-xl border border-[#D9D9D9] text-sm font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50 transition-colors"
          >
            <RefreshCw size={14} />
            {resetConfig.isPending ? "Resetting…" : "Reset to defaults"}
          </button>
          <button
            onClick={() => updateConfig.mutate()}
            disabled={updateConfig.isPending}
            className="flex items-center gap-2 bg-[#224C87] text-white px-4 py-2 rounded-xl text-sm font-medium hover:bg-[#1a3d6e] disabled:opacity-50 transition-colors"
          >
            <Save size={15} />
            {updateConfig.isPending ? "Saving…" : "Save settings"}
          </button>
        </div>
      </Section>
    </div>
  );
}
