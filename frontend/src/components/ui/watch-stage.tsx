"use client";

import type { ReactNode } from "react";
import { RectangleHorizontal } from "lucide-react";
import { CARD_SHELL } from "@/components/ui/section-card";
import { cn } from "@/lib/utils";

/**
 * Watch column + optional chapters rail.
 * Source order is player → companion → below so a one-column page keeps
 * chapters under the picture (YouTube), not under Summary/Files.
 */
export const WATCH_GRID =
  "grid w-full grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_25rem] lg:items-start";

const COMPANION_COL =
  "min-w-0 lg:col-start-2 lg:row-start-1 lg:row-span-2 lg:sticky lg:top-6 lg:self-start";
const COMPANION_PANEL = cn(CARD_SHELL, "flex min-h-0 flex-col overflow-hidden");
const COMPANION_SHELL = "flex min-h-0 flex-1 flex-col overflow-hidden";
export const COMPANION_TABS_ROW = "shrink-0 border-b border-border px-5 pb-3 pt-3";
export const COMPANION_BODY = "min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 pb-5 pt-4";
/** Chapters / transcript: search stays put, the list scrolls. */
export const COMPANION_BODY_PINNED =
  "flex min-h-0 flex-1 flex-col overflow-hidden overscroll-contain px-5 pb-5 pt-4";

export const WATCH_BELOW = "space-y-6";

export function WatchStage({
  title,
  toolbar,
  player,
  companion,
  below,
  theater = false,
  onTheaterChange,
}: {
  title?: ReactNode;
  toolbar?: ReactNode;
  player: ReactNode;
  companion?: ReactNode;
  below?: ReactNode;
  theater?: boolean;
  onTheaterChange?: (next: boolean) => void;
}) {
  const rail = Boolean(companion) && !theater;
  const showTheater = Boolean(companion) && Boolean(onTheaterChange);

  function setTheater(next: boolean) {
    onTheaterChange?.(next);
  }

  return (
    <div className={cn(rail ? WATCH_GRID : "flex w-full flex-col gap-6", theater && "leap-watch-wide")}>
      <div className={cn("min-w-0 w-full", rail && "lg:col-start-1 lg:row-start-1")}>
        <div
          id="leap-watch-player"
          className={cn(
            CARD_SHELL,
            "overflow-hidden max-sm:-mx-4 max-sm:rounded-none max-sm:border-x-0 max-sm:shadow-none",
          )}
        >
          {player}
          {(title || toolbar || showTheater) && (
            <div className="space-y-3 px-4 py-4 sm:px-5">
              {(title || showTheater) && (
                <div className="flex items-start gap-3">
                  <div className="min-w-0 flex-1">{title}</div>
                  {showTheater && (
                    <button
                      type="button"
                      aria-pressed={theater}
                      aria-label={theater ? "Default Screen" : "Wide Screen"}
                      title={theater ? "Default Screen" : "Wide Screen"}
                      onClick={() => setTheater(!theater)}
                      className={cn(
                        "pressable hidden shrink-0 items-center gap-1.5 rounded-xl border px-2.5 py-1.5 text-xs font-medium lg:inline-flex",
                        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30",
                        theater
                          ? "border-primary/40 bg-primary/10 text-primary"
                          : "border-border bg-card text-muted-foreground hover:border-primary/40 hover:text-primary",
                      )}
                    >
                      <RectangleHorizontal size={14} aria-hidden />
                      {theater ? "Default Screen" : "Wide Screen"}
                    </button>
                  )}
                </div>
              )}
              {toolbar}
            </div>
          )}
        </div>
      </div>

      {companion && (
        <div className={cn(rail ? COMPANION_COL : "min-w-0")}>
          <div
            className={cn(
              COMPANION_PANEL,
              rail ? "lg:max-h-[calc(100dvh-5.5rem)]" : "max-h-[min(32rem,70dvh)]",
            )}
          >
            <div className={COMPANION_SHELL}>{companion}</div>
          </div>
        </div>
      )}

      {below && (
        <div className={cn("min-w-0", rail && "lg:col-start-1 lg:row-start-2")}>{below}</div>
      )}
    </div>
  );
}
