"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ME_QUERY_KEY, useMe } from "@/lib/react-query";
import { Save } from "lucide-react";
import { apiClient } from "@/api/client";
import { extractApiError } from "@/lib/utils";
import { FILTER_CONTROL } from "@/lib/filter-field-classes";
import { ActionButton } from "@/components/ui/action-button";
import { Field } from "@/components/ui/field";
import { NativeSelect } from "@/components/ui/native-select";
import { Toast } from "@/components/ui/toast";
import { useToast } from "@/hooks/use-toast";
import { useTimezones } from "@/hooks/use-references";
import { TOAST_SHORT } from "@/lib/constants";
import { SectionCard } from "./shared";
import type { QuotaStatus } from "./types";
import { formatMonthYear } from "./format";

export function AccountPanel() {
  const qc = useQueryClient();
  const { toast, show: showToast, dismiss: dismissToast } = useToast(TOAST_SHORT);
  const { data: timezones = [] } = useTimezones();

  const [profile, setProfile] = useState({ full_name: "", email: "", timezone: "" });

  const { data: userData } = useMe();
  const { data: quotaData } = useQuery<QuotaStatus>({
    queryKey: ["user-quota"],
    queryFn: async () => (await apiClient.get<QuotaStatus>("/users/me/quota")).data,
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
      qc.invalidateQueries({ queryKey: ME_QUERY_KEY });
      showToast("success", "Profile saved");
    },
    onError: (err) => showToast("error", extractApiError(err), null),
  });

  const planName = quotaData?.subscription?.plan?.display_name ?? null;
  const memberSince = formatMonthYear(userData?.created_at);
  const roleLabel = userData?.role
    ? userData.role.charAt(0).toUpperCase() + userData.role.slice(1)
    : null;

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
            >
              {timezones.map((tz) => (
                <option key={tz.value} value={tz.value}>{tz.label}</option>
              ))}
              {!timezones.some((t) => t.value === profile.timezone) && profile.timezone && (
                <option value="__custom__">{profile.timezone} (custom)</option>
              )}
            </NativeSelect>
          </Field>
        </div>
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
