"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Save } from "lucide-react";
import { apiClient } from "@/api/client";
import { cn, extractApiError } from "@/lib/utils";
import { FILTER_CONTROL } from "@/lib/filter-field-classes";
import { ActionButton } from "@/components/ui/action-button";
import { Field } from "@/components/ui/field";
import { NativeSelect } from "@/components/ui/native-select";
import { Toast } from "@/components/ui/toast";
import { useToast } from "@/hooks/use-toast";
import { useTimezones } from "@/hooks/use-references";
import { TOAST_SHORT } from "@/lib/constants";
import { SectionCard, StatRow } from "./shared";
import type { QuotaStatus, UserMe, UserStats } from "./types";
import { COUNT_FORMATTER, fmtNum, formatMonthYear, formatTotalDuration } from "./format";

export function AccountPanel() {
  const qc = useQueryClient();
  const { toast, show: showToast, dismiss: dismissToast } = useToast(TOAST_SHORT);
  const { data: timezones = [] } = useTimezones();

  const [profile, setProfile] = useState({ full_name: "", email: "", timezone: "" });

  const { data: userData } = useQuery<UserMe>({
    queryKey: ["user-me"],
    queryFn: async () => (await apiClient.get<UserMe>("/users/me")).data,
  });
  const { data: quotaData } = useQuery<QuotaStatus>({
    queryKey: ["user-quota"],
    queryFn: async () => (await apiClient.get<QuotaStatus>("/users/me/quota")).data,
  });
  const { data: statsData } = useQuery<UserStats>({
    queryKey: ["user-stats"],
    queryFn: async () => (await apiClient.get<UserStats>("/users/me/stats")).data,
  });

  useEffect(() => {
    if (!userData) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrate form from fetched user
    setProfile({
      full_name: userData.full_name ?? "",
      email: userData.email,
      timezone: userData.timezone,
    });
  }, [userData]);

  const updateProfile = useMutation({
    mutationFn: () =>
      apiClient.patch("/users/me", { full_name: profile.full_name, timezone: profile.timezone }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["user-me"] });
      showToast("success", "Profile saved");
    },
    onError: (err) => showToast("error", extractApiError(err), null),
  });

  const planName = quotaData?.subscription?.plan?.display_name ?? null;
  const recLimit = quotaData?.recordings?.limit ?? null;
  const stLimitGb = quotaData?.storage?.limit_gb ?? null;
  const ctLimit = quotaData?.concurrent_tasks?.limit ?? null;
  const ajLimit = quotaData?.automation_jobs?.limit ?? null;
  const memberSince = formatMonthYear(userData?.created_at);
  const roleLabel = userData?.role
    ? userData.role.charAt(0).toUpperCase() + userData.role.slice(1)
    : null;

  // On an unlimited plan every quota row reads "0 / ∞", which is four rows of
  // noise. Show the usage figure alone and say once that the plan is unlimited.
  const unlimitedPlan =
    !!quotaData && recLimit == null && stLimitGb == null && ctLimit == null && ajLimit == null;
  const quota = (used: string, limit: string) => (unlimitedPlan ? used : `${used} / ${limit}`);

  const statRows: { label: string; value: string }[] = [];
  if (quotaData) {
    statRows.push({
      label: "Recordings this month",
      value: quota(COUNT_FORMATTER.format(quotaData.recordings?.used ?? 0), fmtNum(recLimit)),
    });
    statRows.push({
      label: "Storage",
      value: `${quota((quotaData.storage?.used_gb ?? 0).toFixed(2), fmtNum(stLimitGb))} GB`,
    });
    statRows.push({
      label: "Concurrent tasks",
      value: quota(String(quotaData.concurrent_tasks?.used ?? 0), fmtNum(ctLimit)),
    });
    statRows.push({
      label: "Automation jobs",
      value: quota(String(quotaData.automation_jobs?.used ?? 0), fmtNum(ajLimit)),
    });
  }
  if (statsData) {
    statRows.push({
      label: "Transcribed, all time",
      value: formatTotalDuration(statsData.transcription_total_seconds),
    });
    statRows.push({
      label: "Recordings, all time",
      value: COUNT_FORMATTER.format(statsData.recordings_total),
    });
  }

  return (
    <div className="space-y-6">
      {userData ? (
        <div className="rounded-2xl border border-border bg-card p-6 shadow-sm sm:p-7">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              {/* Not a heading: the page <h1> is "Settings", and an <h2> at this
                  size would out-rank it in the document outline. */}
              <p className="truncate text-xl font-semibold text-foreground">
                {userData.full_name?.trim() || userData.email}
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                {userData.email}
                {memberSince !== "—" && <span> · Member since {memberSince}</span>}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {planName && (
                <span className="rounded-full bg-primary/8 px-3 py-1 text-xs font-semibold text-primary">
                  {planName}
                </span>
              )}
              {roleLabel && (
                <span className="rounded-full bg-muted px-3 py-1 text-xs font-medium text-secondary-foreground">
                  {roleLabel}
                </span>
              )}
            </div>
          </div>

          {statRows.length > 0 && (
            <div className="mt-6 grid grid-cols-1 gap-x-12 border-t border-border pt-4 sm:grid-cols-2">
              {statRows.map((r) => (
                <StatRow key={r.label} label={r.label} value={r.value} />
              ))}
            </div>
          )}

          {/* Plans are assigned by an administrator, so seeing a limit without
              knowing how to raise it is a dead end. */}
          {quotaData && (
            <p className="mt-4 text-xs text-muted-foreground">
              {unlimitedPlan
                ? "This plan has no usage limits. Plans are managed by an administrator."
                : "Need different limits? Plans are managed by an administrator — ask yours to adjust the plan on this account."}
            </p>
          )}
        </div>
      ) : (
        <div className="h-40 animate-pulse rounded-2xl border border-border bg-card" />
      )}

      <SectionCard title="Profile">
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          <Field label="Full name">
            <input
              type="text"
              value={profile.full_name}
              onChange={(e) => setProfile((p) => ({ ...p, full_name: e.target.value }))}
              placeholder="Your name"
              className={FILTER_CONTROL}
            />
          </Field>
          <Field label="Email" hint="Your sign-in address. Contact an administrator to change it.">
            <input
              type="email"
              value={profile.email}
              disabled
              className={cn(FILTER_CONTROL, "cursor-not-allowed bg-muted text-muted-foreground")}
            />
          </Field>
        </div>
        <Field label="Timezone">
          <NativeSelect
            value={
              timezones.some((t) => t.value === profile.timezone) ? profile.timezone : "__custom__"
            }
            onChange={(e) => {
              if (e.target.value !== "__custom__") {
                setProfile((p) => ({ ...p, timezone: e.target.value }));
              }
            }}
            wrapperClassName="max-w-sm"
          >
            {timezones.map((tz) => (
              <option key={tz.value} value={tz.value}>{tz.label}</option>
            ))}
            {!timezones.some((t) => t.value === profile.timezone) && profile.timezone && (
              <option value="__custom__">{profile.timezone} (custom)</option>
            )}
          </NativeSelect>
        </Field>
        <div className="flex justify-end">
          <ActionButton
            onClick={() => updateProfile.mutate()}
            isPending={updateProfile.isPending}
            isSuccess={updateProfile.isSuccess}
            icon={<Save />}
            pendingLabel="Saving…"
          >
            Save profile
          </ActionButton>
        </div>
      </SectionCard>

      {toast && (
        <Toast
          key={toast.serial}
          type={toast.type}
          message={toast.msg}
          exiting={toast.exiting}
          onDismiss={dismissToast}
        />
      )}
    </div>
  );
}
