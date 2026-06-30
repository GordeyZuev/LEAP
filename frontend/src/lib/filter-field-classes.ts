/** Shared Tailwind classes for resource filter toolbars (recordings, presets, …). */

export const FILTER_CARD =
  "rounded-2xl border border-border/90 bg-card shadow-sm p-4 sm:p-5 mb-6 space-y-5 overflow-visible";

export const FILTER_LABEL = "block text-xs font-medium text-muted-foreground mb-1.5";

// All controls share one height (2.875rem = 46px) so they line up exactly with
// the segmented toggle group (FILTER_SEGMENT_WRAP): its py-2 buttons (36px) plus
// the wrap's p-1 (8px) and 1px border on each side total 46px. Keep these in sync.
export const FILTER_CONTROL =
  "w-full min-h-[2.875rem] px-3 py-2 rounded-xl border border-border bg-card text-sm text-foreground outline-none transition-colors focus:border-primary focus:ring-2 focus:ring-primary/30";

export const FILTER_SELECT =
  "w-full min-h-[2.875rem] pl-3 pr-8 py-2 rounded-xl border border-border bg-card text-sm font-medium text-secondary-foreground outline-none transition-colors focus:border-primary focus:ring-2 focus:ring-primary/30 appearance-none";

/** Segmented toggle group (mapping / include flags). */
export const FILTER_SEGMENT_WRAP =
  "flex w-full rounded-xl border border-border bg-muted p-1 gap-0.5";

export const FILTER_SEGMENT_BTN =
  "flex-1 whitespace-nowrap rounded-lg px-3 py-2 text-center text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/25";

export const FILTER_SEGMENT_ACTIVE = "bg-card text-primary shadow-sm";

export const FILTER_SEGMENT_IDLE = "text-muted-foreground hover:text-secondary-foreground";
