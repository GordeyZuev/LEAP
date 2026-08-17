/** Shared Tailwind classes for list tables (recordings, templates, automation, …). */

/**
 * Card that wraps a list table.
 *
 * `overflow-x-auto` makes the element a scroll container on both axes, which
 * prevents a sticky header from anchoring to the page. Above `xl` the tables
 * fit without horizontal scrolling, so the container is dropped there and the
 * header sticks; below that, horizontal scrolling wins.
 */
export const TABLE_CARD =
  "w-full overflow-x-auto rounded-2xl border border-border bg-card shadow-sm xl:overflow-visible";

/** Header typography — matches the uppercase label idiom used across the app. */
export const TABLE_HEAD_CELL =
  "px-6 py-3 text-xs font-medium uppercase tracking-wide text-muted-foreground";

/** Body: row separators live here, so rows never draw their own borders. */
export const TABLE_BODY = "divide-y divide-border";

/**
 * Body row: same hover feedback on every list.
 *
 * The card no longer clips overflow (that would break the sticky header), so a
 * tinted last row would paint square corners over the card's rounded edge — the
 * outer cells of the last row round themselves instead.
 */
export const TABLE_ROW_CORNERS =
  "last:[&>td:first-child]:rounded-bl-2xl last:[&>td:last-child]:rounded-br-2xl";

export const TABLE_ROW = `transition-colors hover:bg-muted ${TABLE_ROW_CORNERS}`;
