/** Helpers for POST /recordings/{id}/run and bulk run responses. */

export interface RunOperationResponse {
  success?: boolean;
  task_id?: string | null;
  message?: string | null;
  awaiting_source?: boolean;
  recording_status?: string | null;
  mts?: {
    outcome?: string;
    conversion_progress?: number | null;
    conversion_state?: string | null;
  } | null;
}

export function runToastMessage(data: RunOperationResponse | undefined): { kind: "success" | "info"; text: string } {
  if (data?.awaiting_source) {
    const progress =
      data.mts?.conversion_progress != null ? ` (${data.mts.conversion_progress}%)` : "";
    return {
      kind: "info",
      text: data.message ?? `Waiting for MTS Link${progress}`,
    };
  }
  if (data?.task_id) {
    return { kind: "success", text: data.message ?? "Pipeline started" };
  }
  return { kind: "success", text: data?.message ?? "Done" };
}
