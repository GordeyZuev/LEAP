/** Thumb box for an overlay scrollbar that stops short of a rounded corner. */
export function scrollThumbGeometry(
  scrollTop: number,
  scrollHeight: number,
  clientHeight: number,
  insetTopPx: number,
  insetBottomPx = insetTopPx,
  minThumb = 24,
): { top: number; height: number } | null {
  if (clientHeight <= 0 || scrollHeight <= clientHeight + 1) return null;
  const available = clientHeight - insetTopPx - insetBottomPx;
  if (available < 8) return null;
  const height = Math.min(available, Math.max(Math.min(minThumb, available), (clientHeight / scrollHeight) * available));
  const maxOffset = available - height;
  const range = scrollHeight - clientHeight;
  const top = insetTopPx + (range > 0 ? (scrollTop / range) * maxOffset : 0);
  return { top, height };
}

/** `getComputedStyle` returns custom properties as specified, so rem stays rem. */
export function cssLengthToPx(raw: string, rootFontPx: number): number {
  const value = raw.trim();
  const amount = Number.parseFloat(value);
  if (!Number.isFinite(amount)) return 0;
  if (value.endsWith("rem")) return amount * rootFontPx;
  return amount;
}
