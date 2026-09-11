# Web UI conventions (Next.js)

The app lives in `frontend/` (Next.js). This note is for **motion and shared controls**, not API contracts.

## Motion

- **CSS only** — no `motion` / Framer Motion. Enter/exit for dialogs uses `useExitPresence` plus transitions (interruptible). Keyframes stay for one-shot enters: toasts, dropdowns, auth/landing panels, empty/error states.
- **Dialog overlay** — keep pointer events until unmount. `inert` / `pointer-events-none` on a fading overlay lets clicks hit the page underneath.
- **App navigation** — `animate-page-in` is opacity only (~120ms). Do not put scale/translate on every route change.
- **Theme** — `applyThemeInstantly` in `frontend/src/lib/theme.ts` disables transitions for one frame so a theme flip does not smear.
- **Reduced motion** — `frontend/src/app/globals.css` short-circuits animation and transition duration globally.

## Press feedback

Class **`.pressable`** (same file): color/background/border/opacity/scale, 150ms, `scale(0.96)` on `:active:not(:disabled)`.

Use it on primary chrome: `ActionButton`, pagination, tabs, create placeholders, landing CTAs, sidebar logout/collapse, mobile menu. **Do not** put it on filter segments, chips, or table sort headers — those stay color-only (`FILTER_SEGMENT_BTN`).

Name transition properties. Do not use `transition-all`.

## Icons

`ActionButton` pending/success icons cross-fade in CSS (`opacity`, `scale` 0.25↔1, `blur(4px)`). Do not swap Lucide nodes with `display: none` if you need an exit.

## Form controls

- **Single select** — `NativeSelect` / `FilterSelect`. When `value` is non-empty, the trigger uses `FILTER_CONTROL_FILLED` (`border-primary/30`, `bg-primary/5`, primary label text).
- **Multi select** — `ChecklistPicker` (and toolbar `FilterMultiSelect`) tint the whole trigger when at least one item is selected; chips inside copy presets use the same primary accent.
- **Config editors** — template, preset, Run with config, and Edit configuration share `OverrideSection` rows and `Disclosure` platform blocks; see [TEMPLATES.md](TEMPLATES.md).

## Related

- [CHANGELOG.md](../CHANGELOG.md) — dated “Frontend motion” notes
- [VIDEO_DELIVERY.md](VIDEO_DELIVERY.md) — player URLs, not UI chrome
