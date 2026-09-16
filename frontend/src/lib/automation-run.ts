export interface AffectedRecording {
  id: number;
  name: string;
  template_id: number;
  template_name: string;
}

export interface AutomationPreviewResult {
  status: string;
  job_id?: number;
  synced_count?: number;
  sources_synced?: number[];
  recordings_found?: number;
  matched_count?: number;
  unmatched_count?: number;
  would_process?: AffectedRecording[];
  error?: string;
}

export interface CeleryTaskStatus {
  task_id: string;
  state: string;
  status: string;
  progress: number;
  result: AutomationPreviewResult | null;
  error: string | null;
}

export const RUN_JOB_CONFIRM = {
  title: "Run this job?",
  description:
    "Matching recordings start processing. Unsaved edits on this page are ignored. Refresh sources if you need the latest catalog from Zoom or MTS.",
  confirmLabel: "Run job",
} as const;

export const RUN_JOB_CONFIRM_LIST = {
  title: "Run this job?",
  description:
    "Matching recordings start processing using this job’s saved settings (including whether sources refresh first).",
  confirmLabel: "Run job",
} as const;

export function isCeleryInFlight(state: string | undefined): boolean {
  return state === "PENDING" || state === "PROCESSING" || state === "RETRY" || state === "STARTED";
}
