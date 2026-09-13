export interface PlaylistPlayableItem {
  id: number;
  playable: boolean;
}

export function firstPlayable<T extends PlaylistPlayableItem>(items: T[]): T | undefined {
  return items.find((i) => i.playable);
}

export function nextPlayable<T extends PlaylistPlayableItem>(items: T[], fromId: number): T | undefined {
  const idx = items.findIndex((i) => i.id === fromId);
  if (idx < 0) return firstPlayable(items);
  return items.slice(idx + 1).find((i) => i.playable);
}

export function lastIndexAtOrBefore(items: { start: number }[], time: number): number {
  for (let i = items.length - 1; i >= 0; i--) {
    if (time >= items[i].start) return i;
  }
  return -1;
}
