/** Shared Tailwind classes for resource filter toolbars (recordings, presets, …). */

/** Toolbar shell for list-page filters — flat on the page background;
 *  the data table below carries the elevated card surface. */
export const FILTER_TOOLBAR = "mb-5 space-y-4 overflow-visible";

export const FILTER_LABEL = "block text-xs font-medium text-muted-foreground mb-1.5";

/** FilterBar control slot — grows for dropdowns, stays compact for SegmentedField. */
export const FILTER_BAR_CONTROL =
  "min-w-[11rem] flex-1 basis-[11rem] max-w-full has-[[data-segmented-field]]:min-w-0 has-[[data-segmented-field]]:w-auto has-[[data-segmented-field]]:flex-none has-[[data-segmented-field]]:basis-auto";

// All controls share one height (2.875rem = 46px) so they line up exactly with
// the segmented toggle group (FILTER_SEGMENT_WRAP): its py-2 buttons (36px) plus
// the wrap's p-1 (8px) and 1px border on each side total 46px. Keep these in sync.
// Controls use `border-input`, not `border-border`. The two tokens carry the
// same hue but different jobs: `border` is a hairline divider, `input` is the
// boundary that tells the user a field is editable and has to clear 3:1.
export const FILTER_CONTROL =
  "w-full min-h-[2.875rem] px-3 py-2 rounded-xl border border-input bg-card text-sm text-foreground outline-none transition-colors focus:border-primary focus:ring-2 focus:ring-primary/30";

export const FILTER_SELECT =
  "w-full min-h-[2.875rem] pl-3 pr-8 py-2 rounded-xl border border-input bg-card text-sm font-medium text-secondary-foreground outline-none transition-colors focus:border-primary focus:ring-2 focus:ring-primary/30 appearance-none";

/** Segmented toggle group (mapping / include flags). */
export const FILTER_SEGMENT_WRAP =
  "inline-flex max-w-full items-center min-h-[2.875rem] rounded-xl border border-border bg-muted p-1 gap-0.5";

export const FILTER_SEGMENT_BTN =
  "shrink-0 whitespace-nowrap rounded-lg px-3.5 py-2 text-center text-sm font-medium transition-[color,background-color,box-shadow,transform] duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/25 active:scale-[0.98]";

export const FILTER_SEGMENT_ACTIVE =
  "bg-card text-foreground shadow-sm ring-1 ring-border";

export const FILTER_SEGMENT_IDLE =
  "text-muted-foreground hover:bg-card/70 hover:text-secondary-foreground";
