export const OPERATIONAL_STATES = ["in_progress", "waiting_source", "paused", "error"] as const;
export type OperationalState = typeof OPERATIONAL_STATES[number];
export const OPERATIONAL_STATE_LABEL: Record<OperationalState, string> = {
  in_progress: "In progress",
  waiting_source: "Waiting for source",
  paused: "Paused",
  error: "With errors",
};
export function parseOperationalState(value: string | null): OperationalState | null {
  return OPERATIONAL_STATES.find((state) => state === value) ?? null;
}
export function operationalStateHref(state: OperationalState): string {
  return `/recordings?operational_state=${state}`;
}
