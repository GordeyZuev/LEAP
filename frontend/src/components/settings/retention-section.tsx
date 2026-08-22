"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Save } from "lucide-react";
import { apiClient } from "@/api/client";
import { extractApiError } from "@/lib/utils";
import { ActionButton } from "@/components/ui/action-button";
import { Field } from "@/components/ui/field";
import { NumberInput } from "@/components/ui/number-input";
import { Toast } from "@/components/ui/toast";
import { useToast } from "@/hooks/use-toast";
import { TOAST_SHORT } from "@/lib/constants";
import type { RetentionConfig, UserConfig } from "./types";

const DEFAULT_RETENTION: RetentionConfig = {
  soft_delete_days: 3,
  hard_delete_days: 30,
  auto_expire_days: 90,
};

export function RetentionSection() {
  const qc = useQueryClient();
  const { toast, show: showToast, dismiss: dismissToast } = useToast(TOAST_SHORT);
  const [retention, setRetention] = useState<RetentionConfig>(DEFAULT_RETENTION);

  const { data: userConfig } = useQuery<UserConfig>({
    queryKey: ["user-config"],
    queryFn: async () => (await apiClient.get<UserConfig>("/users/me/config")).data,
  });

  /* eslint-disable react-hooks/set-state-in-effect -- hydrate retention from fetched user config */
  useEffect(() => {
    if (!userConfig?.config_data?.retention) return;
    const r = userConfig.config_data.retention;
    setRetention({
      soft_delete_days: r.soft_delete_days ?? DEFAULT_RETENTION.soft_delete_days,
      hard_delete_days: r.hard_delete_days ?? DEFAULT_RETENTION.hard_delete_days,
      auto_expire_days: r.auto_expire_days ?? DEFAULT_RETENTION.auto_expire_days,
    });
  }, [userConfig]);
  /* eslint-enable react-hooks/set-state-in-effect */

  const save = useMutation({
    mutationFn: () =>
      apiClient.patch("/users/me/config", {
        retention,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["user-config"] });
      showToast("success", "Retention policy saved");
    },
    onError: (err) => showToast("error", extractApiError(err), null),
  });

  return (
    <>
      <p className="mb-5 text-sm text-muted-foreground">
        Account-level storage policy. Video processing defaults live in your base template.
      </p>
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-3">
        <Field label="Soft delete (days)">
          <NumberInput
            integer
            min={1}
            value={retention.soft_delete_days}
            onCommit={(v) => setRetention((c) => ({ ...c, soft_delete_days: v }))}
          />
        </Field>
        <Field label="Hard delete (days)">
          <NumberInput
            integer
            min={1}
            value={retention.hard_delete_days}
            onCommit={(v) => setRetention((c) => ({ ...c, hard_delete_days: v }))}
          />
        </Field>
        <Field label="Auto-expire (days)">
          <NumberInput
            integer
            min={1}
            value={retention.auto_expire_days}
            onCommit={(v) => setRetention((c) => ({ ...c, auto_expire_days: v }))}
          />
        </Field>
      </div>
      <div className="mt-5 flex justify-end">
        <ActionButton
          variant="primary"
          onClick={() => save.mutate()}
          isPending={save.isPending}
          icon={<Save size={16} />}
          pendingLabel="Saving…"
        >
          Save retention
        </ActionButton>
      </div>

      {toast && (
        <Toast
          key={toast.serial}
          type={toast.type}
          message={toast.msg}
          exiting={toast.exiting}
          onDismiss={dismissToast}
        />
      )}
    </>
  );
}
