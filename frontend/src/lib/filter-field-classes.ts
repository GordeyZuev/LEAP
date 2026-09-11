/** Shared Tailwind classes for resource filter toolbars (recordings, presets, …). */

/** Toolbar shell for list-page filters — flat on the page background;
 *  the data table below carries the elevated card surface. */
export const FILTER_TOOLBAR = "mb-5 space-y-4 overflow-visible";

export const FILTER_LABEL = "block text-xs font-medium text-muted-foreground mb-1.5";

/** FilterBar control slot — full width on narrow viewports; segmented groups stretch evenly. */
export const FILTER_BAR_CONTROL =
  "w-full min-w-0 max-w-full sm:min-w-[11rem] sm:flex-1 sm:basis-[11rem] " +
  "[&_[data-segmented-field]]:w-full sm:[&_[data-segmented-field]]:w-fit " +
  "[&_[data-segmented-field]_[role=radiogroup]]:flex sm:[&_[data-segmented-field]_[role=radiogroup]]:inline-flex " +
  "[&_[data-segmented-field]_[role=radiogroup]_button]:min-w-0 sm:[&_[data-segmented-field]_[role=radiogroup]_button]:min-w-[auto] " +
  "[&_[data-segmented-field]_[role=radiogroup]_button]:flex-1 sm:[&_[data-segmented-field]_[role=radiogroup]_button]:flex-none";

// All controls share one height (2.875rem = 46px) so they line up exactly with
// the segmented toggle group (FILTER_SEGMENT_CHROME): its py-2 buttons (36px) plus
// the wrap's p-1 (8px) and 1px border on each side total 46px. Keep these in sync.
// Controls use `border-input`, not `border-border`. The two tokens carry the
// same hue but different jobs: `border` is a hairline divider, `input` is the
// boundary that tells the user a field is editable and has to clear 3:1.
export const FILTER_CONTROL =
  "w-full min-h-[2.875rem] px-3 py-2 rounded-xl border border-input bg-card text-sm text-foreground outline-none transition-colors focus:border-primary focus:ring-2 focus:ring-primary/30";

/** Trigger surface when a value is chosen (single- or multi-select). */
export const FILTER_CONTROL_FILLED =
  "border-primary/30 bg-primary/5";

/** Shared chrome for the segmented (pillow) group — layout is inline vs stretch. */
export const FILTER_SEGMENT_CHROME =
  "items-center min-h-[2.875rem] gap-0.5 rounded-xl border border-border bg-muted p-1";

export const FILTER_SEGMENT_BTN =
  "shrink-0 whitespace-nowrap rounded-lg px-3.5 py-2 text-center text-sm font-medium transition-[color,background-color,box-shadow] duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30";

export const FILTER_SEGMENT_ACTIVE =
  "bg-card text-foreground shadow-sm ring-1 ring-border";

export const FILTER_SEGMENT_IDLE =
  "text-muted-foreground hover:bg-card/70 hover:text-secondary-foreground";

/** Native checkbox. On/off functions use `Toggle`; mutually exclusive options use `SegmentedField`. */
export const CHECKBOX =
  "size-4 shrink-0 rounded border-border accent-primary text-primary focus:ring-2 focus:ring-primary/30";
